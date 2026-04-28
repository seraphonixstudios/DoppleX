from __future__ import annotations

import threading
import os
from typing import Optional
import requests
from security.token_store import store_token, load_token
from encryption.crypto import decrypt, encrypt
from datetime import datetime, timedelta

from oauth.oauth_config import PROVIDERS
from oauth.oauth_flow import login_with_oauth
from db.database import SessionLocal
from models import Account
from encryption.crypto import encrypt
import logging
from utils.audit import log_action

logger = logging.getLogger("you2.oauth")


def _get_or_create_account(provider: str) -> Account:
    with SessionLocal() as db:
        acc = db.query(Account).filter(Account.platform == provider).first()
        if acc is None:
            acc = Account(platform=provider, username=None)
            db.add(acc)
            db.commit()
            db.refresh(acc)
        return acc


def authorize_provider(provider_name: str) -> str:
    cfg = PROVIDERS.get(provider_name)
    if not cfg:
        return f"Unknown provider: {provider_name}"
    try:
        token_resp = login_with_oauth(
            provider_name,
            cfg["authorize_url"],
            cfg["token_url"],
            cfg["client_id"],
            redirect_port=cfg["redirect_port"],
            scopes=cfg["scopes"],
        )
    except Exception as e:
        logger.exception("OAuth flow failed for %s: %s", provider_name, e)
        return f"OAuth flow failed for {provider_name}: {e}"
    if not token_resp:
        return f"OAuth flow canceled or no token returned for {provider_name}"
    access = token_resp.get("access_token") or token_resp.get("token") or token_resp.get("token_type")
    refresh = token_resp.get("refresh_token")
    expires_in = token_resp.get("expires_in")
    refresh_expires_in = token_resp.get("refresh_expires_in")
    with SessionLocal() as db:
        acc = db.query(Account).filter(Account.platform == provider_name).first()
        if not acc:
            acc = Account(platform=provider_name, username=None)
            db.add(acc)
        if access:
            acc.token_encrypted = encrypt(access)
            try:
                store_token(provider_name, "token", access)
            except Exception:
                pass
        if refresh:
            acc.refresh_token_encrypted = encrypt(refresh)
            try:
                store_token(provider_name, "refresh_token", refresh)
            except Exception:
                pass
        if expires_in:
            try:
                acc.token_expiry = datetime.utcnow() + timedelta(seconds=int(expires_in))
            except Exception:
                pass
        if refresh_expires_in:
            try:
                acc.refresh_token_expiry = datetime.utcnow() + timedelta(seconds=int(refresh_expires_in))
            except Exception:
                pass
        db.commit()
        db.refresh(acc)
    log_action("oauth_authorize", account_id=acc.id, status="success", details=provider_name)
    return f"Authorized {provider_name} (account_id={acc.id})"

def refresh_provider(provider_name: str) -> dict:
    cfg = PROVIDERS.get(provider_name)
    if not cfg:
        return {"ok": False, "error": f"Unknown provider: {provider_name}"}
    # Retrieve refresh token from DB or OS store
    with SessionLocal() as db:
        acc = db.query(Account).filter(Account.platform == provider_name).first()
        if not acc:
            return {"ok": False, "error": "No account configured"}
        refresh_token = None
        if acc.refresh_token_encrypted:
            try:
                refresh_token = decrypt(acc.refresh_token_encrypted)  # type: ignore
            except Exception:
                refresh_token = None
        if not refresh_token:
            try:
                refresh_token = load_token(provider_name, "refresh_token")
            except Exception:
                refresh_token = None
    if not refresh_token:
        return {"ok": False, "error": "No refresh token available"}
    payload = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': cfg['client_id'],
    }
    if cfg.get('client_secret'):
        payload['client_secret'] = cfg['client_secret']
    try:
        resp = requests.post(cfg['token_url'], data=payload, timeout=20)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    if resp.status_code not in (200, 201):
        return {"ok": False, "error": resp.text}
    data = resp.json()
    access = data.get('access_token') or data.get('token')
    refresh = data.get('refresh_token', refresh_token)
    expires_in = data.get('expires_in')
    with SessionLocal() as db:
        acc = db.query(Account).filter(Account.platform == provider_name).first()
        if not acc:
            return {"ok": False, "error": "Account disappeared during refresh"}
        if access:
            acc.token_encrypted = encrypt(access)
        if refresh:
            acc.refresh_token_encrypted = encrypt(refresh)
        if expires_in:
            try:
                acc.token_expiry = datetime.utcnow() + timedelta(seconds=int(expires_in))
            except Exception:
                pass
        if data.get('refresh_expires_in'):
            try:
                acc.refresh_token_expiry = datetime.utcnow() + timedelta(seconds=int(data['refresh_expires_in']))
            except Exception:
                pass
        db.commit()
        db.refresh(acc)
    try:
        if access:
            store_token(provider_name, 'token', access)
        if refresh:
            store_token(provider_name, 'refresh_token', refresh)
    except Exception:
        pass
    log_action("oauth_refresh", account_id=acc.id, status="success", details=provider_name)
    return {"ok": True, "access_token": access, "expires_in": expires_in}
