from __future__ import annotations

from encryption.crypto import decrypt
from models import Account
import requests


def post_text(account: Account, content: str) -> dict:
    token = None
    if getattr(account, "token_encrypted", None):
        token = decrypt(account.token_encrypted)
    if not token:
        return {"ok": False, "error": "Missing X bearer token."}
    url = "https://api.twitter.com/2/tweets"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"text": content}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code in (200, 201):
            return {"ok": True, "data": resp.json()}
        return {"ok": False, "error": resp.text}
    except Exception as e:
        return {"ok": False, "error": str(e)}
