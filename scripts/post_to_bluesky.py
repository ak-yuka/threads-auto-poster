import os
import re
from datetime import timezone

import regex
import requests

from sheet_utils import HEADER_ROWS, determine_theme, get_worksheet, jst_now, mark_posted, pick_text

BLUESKY_PDS = "https://bsky.social"

URL_RE = re.compile(r"https?://[^\s]+")
YOUTUBE_RE = re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/)")

BLUESKY_MAX_GRAPHEMES = 300
BLUESKY_MAX_BYTES = 3000
ELLIPSIS = "…"


def truncate_for_bluesky(text):
    """Bluesky投稿本文の上限(300グラフェム/3000バイト)を超える場合に末尾を切り詰める"""
    graphemes = regex.findall(r"\X", text)
    if len(graphemes) <= BLUESKY_MAX_GRAPHEMES and len(text.encode("utf-8")) <= BLUESKY_MAX_BYTES:
        return text

    limit = min(len(graphemes), BLUESKY_MAX_GRAPHEMES) - len(ELLIPSIS)
    truncated = graphemes[:limit]
    while len(("".join(truncated) + ELLIPSIS).encode("utf-8")) > BLUESKY_MAX_BYTES:
        truncated = truncated[:-1]
    return "".join(truncated) + ELLIPSIS


def raise_with_body(response):
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        raise requests.exceptions.HTTPError(f"{exc}: {response.text}", response=response) from None


def build_facets(text):
    facets = []
    for m in URL_RE.finditer(text):
        byte_start = len(text[: m.start()].encode("utf-8"))
        byte_end = len(text[: m.end()].encode("utf-8"))
        facets.append(
            {
                "index": {"byteStart": byte_start, "byteEnd": byte_end},
                "features": [{"$type": "app.bsky.richtext.facet#link", "uri": m.group(0)}],
            }
        )
    return facets


def build_youtube_embed(access_jwt, url):
    oembed = requests.get(
        "https://www.youtube.com/oembed",
        params={"url": url, "format": "json"},
        timeout=15,
    )
    raise_with_body(oembed)
    meta = oembed.json()

    thumb = requests.get(meta["thumbnail_url"], timeout=15)
    raise_with_body(thumb)
    upload = requests.post(
        f"{BLUESKY_PDS}/xrpc/com.atproto.repo.uploadBlob",
        headers={
            "Authorization": f"Bearer {access_jwt}",
            "Content-Type": thumb.headers.get("Content-Type", "image/jpeg"),
        },
        data=thumb.content,
        timeout=30,
    )
    raise_with_body(upload)

    return {
        "$type": "app.bsky.embed.external",
        "external": {
            "uri": url,
            "title": meta.get("title", url),
            "description": meta.get("author_name", ""),
            "thumb": upload.json()["blob"],
        },
    }


def post_to_bluesky(text):
    handle = os.environ["BLUESKY_HANDLE"]
    app_password = os.environ["BLUESKY_APP_PASSWORD"]

    truncated_text = truncate_for_bluesky(text)
    if truncated_text != text:
        print(f"投稿本文が上限({BLUESKY_MAX_GRAPHEMES}グラフェム)を超えていたため切り詰めました")
    text = truncated_text

    session = requests.post(
        f"{BLUESKY_PDS}/xrpc/com.atproto.server.createSession",
        json={"identifier": handle, "password": app_password},
        timeout=30,
    )
    raise_with_body(session)
    session_data = session.json()
    access_jwt = session_data["accessJwt"]

    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": jst_now().astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    facets = build_facets(text)
    if facets:
        record["facets"] = facets

    youtube_url = next((u.group(0) for u in URL_RE.finditer(text) if YOUTUBE_RE.search(u.group(0))), None)
    if youtube_url:
        try:
            record["embed"] = build_youtube_embed(access_jwt, youtube_url)
        except requests.RequestException as exc:
            print(f"YouTube埋め込みカードの生成に失敗したためリンクのみで投稿します: {exc}")

    response = requests.post(
        f"{BLUESKY_PDS}/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": f"Bearer {access_jwt}"},
        json={
            "repo": session_data["did"],
            "collection": "app.bsky.feed.post",
            "record": record,
        },
        timeout=30,
    )
    raise_with_body(response)
    return response.json()


def main():
    slot = os.environ["POST_GROUP"]
    ws = get_worksheet(os.environ["BLUESKY_SHEET_ID"])
    rows = ws.get_all_values()[HEADER_ROWS:]

    theme = determine_theme(rows, slot)
    row_number, text = pick_text(ws, rows, theme)
    result = post_to_bluesky(text)

    mark_posted(ws, row_number)
    print(f"投稿完了 slot={slot} theme={theme} row={row_number} uri={result.get('uri')}")


if __name__ == "__main__":
    main()
