import json
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

COL_GROUP = 1
COL_TEXT = 2
COL_POSTED = 3
COL_POSTED_AT = 4
HEADER_ROWS = 1

SLOT_ORDER = ["7", "12", "18", "21"]
JST = timezone(timedelta(hours=9))

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
RETRY_ATTEMPTS = 4
RETRY_BASE_DELAY_SECONDS = 2


def with_retry(fn):
    """Google Sheets APIの一時的なエラー(503など)に対して指数バックオフでリトライする"""
    last_exc = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            return fn()
        except gspread.exceptions.APIError as exc:
            status = exc.response.status_code
            if status not in RETRYABLE_STATUS_CODES or attempt == RETRY_ATTEMPTS - 1:
                raise
            last_exc = exc
            time.sleep(RETRY_BASE_DELAY_SECONDS * (2**attempt))
    raise last_exc


def jst_now():
    return datetime.now(JST)


def cell(row, col):
    return row[col - 1].strip() if len(row) >= col else ""


def get_worksheet(sheet_id):
    creds_info = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
    creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    gc = gspread.authorize(creds)
    return with_retry(lambda: gc.open_by_key(sheet_id).sheet1)


def determine_theme(rows, slot):
    themes = sorted({cell(r, COL_GROUP) for r in rows if cell(r, COL_GROUP)})
    if not themes:
        sys.exit("スプレッドシートにテーマ(Group列)のデータがありません")

    today_str = jst_now().date().isoformat()
    used_today = {cell(r, COL_GROUP) for r in rows if cell(r, COL_POSTED_AT).startswith(today_str)}
    unused = [t for t in themes if t not in used_today]

    idx = SLOT_ORDER.index(slot)
    remaining_slots = SLOT_ORDER[idx:]

    if unused and len(remaining_slots) <= len(unused):
        return random.choice(unused)
    return random.choice(themes)


def pick_text(ws, rows, theme):
    theme_rows = [(i + HEADER_ROWS + 1, r) for i, r in enumerate(rows) if cell(r, COL_GROUP) == theme]
    if not theme_rows:
        sys.exit(f"テーマ '{theme}' の行がスプレッドシートに見つかりません")

    unposted = [(n, r) for n, r in theme_rows if cell(r, COL_POSTED).upper() != "TRUE"]

    if not unposted:
        for n, _ in theme_rows:
            with_retry(lambda n=n: ws.update_cell(n, COL_POSTED, "FALSE"))
        unposted = theme_rows

    row_number, row = random.choice(unposted)
    return row_number, cell(row, COL_TEXT)


def mark_posted(ws, row_number):
    with_retry(lambda: ws.update_cell(row_number, COL_POSTED, "TRUE"))
    with_retry(lambda: ws.update_cell(row_number, COL_POSTED_AT, jst_now().isoformat()))
