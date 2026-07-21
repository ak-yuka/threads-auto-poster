import os
import time

import requests

from sheet_utils import HEADER_ROWS, determine_theme, get_worksheet, mark_posted, pick_text

CONTAINER_POLL_INTERVAL_SECONDS = 5
CONTAINER_POLL_TIMEOUT_SECONDS = 60
PUBLISH_RETRY_ATTEMPTS = 3
PUBLISH_RETRY_DELAY_SECONDS = 5


def raise_with_body(response):
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        raise requests.exceptions.HTTPError(f"{exc}: {response.text}", response=response) from None


def wait_until_container_ready(creation_id, token):
    """Threadsのメディアコンテナは作成直後は処理中(IN_PROGRESS)のことがあり、
    その状態でpublishすると400エラーになるためFINISHEDになるまで待つ"""
    deadline = time.monotonic() + CONTAINER_POLL_TIMEOUT_SECONDS
    while True:
        status_res = requests.get(
            f"https://graph.threads.net/v1.0/{creation_id}",
            params={"fields": "status,error_message", "access_token": token},
            timeout=30,
        )
        raise_with_body(status_res)
        status = status_res.json().get("status")

        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError(f"Threadsコンテナの処理に失敗しました: {status_res.json()}")
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Threadsコンテナが{CONTAINER_POLL_TIMEOUT_SECONDS}秒以内にFINISHEDになりませんでした (status={status})")

        time.sleep(CONTAINER_POLL_INTERVAL_SECONDS)


def publish_container(user_id, creation_id, token):
    """ステータスがFINISHEDになった直後でも、Threads側の反映遅延により
    publishが一時的にMedia Not Found(400)になることがあるためリトライする"""
    for attempt in range(PUBLISH_RETRY_ATTEMPTS):
        publish = requests.post(
            f"https://graph.threads.net/v1.0/{user_id}/threads_publish",
            data={"creation_id": creation_id, "access_token": token},
            timeout=30,
        )
        try:
            raise_with_body(publish)
            return publish.json()
        except requests.exceptions.HTTPError:
            if attempt == PUBLISH_RETRY_ATTEMPTS - 1:
                raise
            time.sleep(PUBLISH_RETRY_DELAY_SECONDS)


def post_to_threads(text):
    user_id = os.environ["THREADS_USER_ID"]
    token = os.environ["THREADS_ACCESS_TOKEN"]

    create = requests.post(
        f"https://graph.threads.net/v1.0/{user_id}/threads",
        data={"media_type": "TEXT", "text": text, "access_token": token},
        timeout=30,
    )
    raise_with_body(create)
    creation_id = create.json()["id"]

    wait_until_container_ready(creation_id, token)

    return publish_container(user_id, creation_id, token)


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
