import json
import os
import random
import sys

import gspread
import requests
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

COL_GROUP = 1
COL_TEXT = 2
COL_POSTED = 3
HEADER_ROWS = 1


def get_worksheet():
    creds_info = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
    creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc.open_by_key(os.environ["SHEET_ID"]).sheet1


def pick_text(ws, group):
    rows = ws.get_all_values()[HEADER_ROWS:]
    group_rows = [
        (i + HEADER_ROWS + 1, r) for i, r in enumerate(rows) if r[COL_GROUP - 1] == group
    ]
    if not group_rows:
        sys.exit(f"グループ '{group}' の行がスプレッドシートに見つかりません")

    unposted = [(n, r) for n, r in group_rows if r[COL_POSTED - 1].strip().upper() != "TRUE"]

    if not unposted:
        for n, _ in group_rows:
            ws.update_cell(n, COL_POSTED, "FALSE")
        unposted = group_rows

    row_number, row = random.choice(unposted)
    return row_number, row[COL_TEXT - 1]


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
    group = os.environ["POST_GROUP"]
    ws = get_worksheet()
    row_number, text = pick_text(ws, group)
    result = post_to_threads(text)
    ws.update_cell(row_number, COL_POSTED, "TRUE")
    print(f"投稿完了 group={group} row={row_number} thread_id={result.get('id')}")


if __name__ == "__main__":
    main()
