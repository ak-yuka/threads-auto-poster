import os

import requests

from sheet_utils import HEADER_ROWS, determine_theme, get_worksheet, mark_posted, pick_text


def post_to_threads(text):
    user_id = os.environ["THREADS_USER_ID"]
    token = os.environ["THREADS_ACCESS_TOKEN"]

    create = requests.post(
        f"https://graph.threads.net/v1.0/{user_id}/threads",
        data={"media_type": "TEXT", "text": text, "access_token": token},
        timeout=30,
    )
    create.raise_for_status()
    creation_id = create.json()["id"]

    publish = requests.post(
        f"https://graph.threads.net/v1.0/{user_id}/threads_publish",
        data={"creation_id": creation_id, "access_token": token},
        timeout=30,
    )
    publish.raise_for_status()
    return publish.json()


def main():
    slot = os.environ["POST_GROUP"]
    ws = get_worksheet(os.environ["SHEET_ID"])
    rows = ws.get_all_values()[HEADER_ROWS:]

    theme = determine_theme(rows, slot)
    row_number, text = pick_text(ws, rows, theme)
    result = post_to_threads(text)

    mark_posted(ws, row_number)
    print(f"投稿完了 slot={slot} theme={theme} row={row_number} thread_id={result.get('id')}")


if __name__ == "__main__":
    main()
