import os
import re
from datetime import timezone

import requests

from sheet_utils import HEADER_ROWS, determine_theme, get_worksheet, jst_now, mark_posted, pick_text

BLUESKY_PDS = "https://bsky.social"

URL_RE = re.compile(r"https?://[^\s]+")
YOUTUBE_RE = re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/)")


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
    oembed.raise_for_status()
    meta = oembed.json()

    thumb = requests.get(meta["thumbnail_url"], timeout=15)
    thumb.raise_for_status()
    upload = requests.post(
        f"{BLUESKY_PDS}/xrpc/com.atproto.repo.uploadBlob",
        headers={
            "Authorization": f"Bearer {access_jwt}",
            "Content-Type": thumb.headers.get("Content-Type", "image/jpeg"),
        },
        data=thumb.content,
        timeout=30,
    )
    upload.raise_for_status()

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

    session = requests.post(
        f"{BLUESKY_PDS}/xrpc/com.atproto.server.createSession",
        json={"identifier": handle, "password": app_password},
        timeout=30,
    )
    session.raise_for_status()
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
    response.raise_for_status()
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
