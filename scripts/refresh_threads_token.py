import base64
import os

import requests
from nacl import encoding, public


def raise_with_body(response):
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        raise requests.exceptions.HTTPError(f"{exc}: {response.text}", response=response) from None


def refresh_threads_token(current_token):
    """長期アクセストークンはGET /refresh_access_tokenで有効期限を60日延長できる。
    交換直後(24時間以内)のトークンはリフレッシュできない制約があるため、
    その場合はThreads API側が400を返す。"""
    res = requests.get(
        "https://graph.threads.net/refresh_access_token",
        params={"grant_type": "th_refresh_token", "access_token": current_token},
        timeout=30,
    )
    raise_with_body(res)
    return res.json()


def get_repo_public_key(owner, repo, github_token):
    res = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}/actions/secrets/public-key",
        headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
        timeout=30,
    )
    raise_with_body(res)
    return res.json()


def encrypt_secret(public_key_b64, secret_value):
    public_key = public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def update_github_secret(owner, repo, github_token, secret_name, secret_value):
    key_info = get_repo_public_key(owner, repo, github_token)
    encrypted_value = encrypt_secret(key_info["key"], secret_value)
    res = requests.put(
        f"https://api.github.com/repos/{owner}/{repo}/actions/secrets/{secret_name}",
        headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
        json={"encrypted_value": encrypted_value, "key_id": key_info["key_id"]},
        timeout=30,
    )
    raise_with_body(res)


def main():
    current_token = os.environ["THREADS_ACCESS_TOKEN"]
    github_token = os.environ["GH_SECRETS_PAT"]
    owner, repo = os.environ["GITHUB_REPOSITORY"].split("/", 1)

    result = refresh_threads_token(current_token)
    new_token = result["access_token"]
    expires_in_days = result.get("expires_in", 0) // 86400

    update_github_secret(owner, repo, github_token, "THREADS_ACCESS_TOKEN", new_token)
    print(f"THREADS_ACCESS_TOKENを更新しました(有効期限: 約{expires_in_days}日後)")


if __name__ == "__main__":
    main()
