import os
from datetime import timezone

import requests

from sheet_utils import HEADER_ROWS, determine_theme, get_worksheet, jst_now, mark_posted, pick_text

BLUESKY_PDS = "https://bsky.social"


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

    created_at = jst_now().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    record = requests.post(
        f"{BLUESKY_PDS}/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": f"Bearer {session_data['accessJwt']}"},
        json={
            "repo": session_data["did"],
            "collection": "app.bsky.feed.post",
            "record": {
                "$type": "app.bsky.feed.post",
                "text": text,
                "createdAt": created_at,
            },
        },
        timeout=30,
    )
    record.raise_for_status()
    return record.json()


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
