from __future__ import annotations

import requests
from encryption.crypto import decrypt


def post_tweet(account, content: str) -> dict:
    # Dry-run by default if no token available; real posting can be enabled via tokens
    token = None
    if getattr(account, 'token_encrypted', None):
        token = decrypt(account.token_encrypted)
    if not token:
        return {"ok": False, "error": "No X token available (dry-run)."}

    url = "https://api.twitter.com/2/tweets"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"text": content}
    resp = requests.post(url, json=payload, headers=headers, timeout=15)
    if resp.status_code in (200, 201):
        data = resp.json()
        return {"ok": True, "data": data}
    else:
        return {"ok": False, "error": resp.text}
