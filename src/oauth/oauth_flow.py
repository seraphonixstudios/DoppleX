from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
import random
import string
import webbrowser
from typing import Optional

import requests


class _CallbackServer(HTTPServer):
    def __init__(self, server_address, RequestHandlerClass):
        super().__init__(server_address, RequestHandlerClass)
        self.code: Optional[str] = None
        self.state: Optional[str] = None


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        self.server.code = code
        self.server.state = state
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"You2.0: Authorization received. You can close this window.")

    def log_message(self, format, *args):  # disable console spam
        return


def _generate_pkce_pair() -> tuple[str, str]:
    code_verifier = base64.urlsafe_b64encode(__import__("os").urandom(40)).decode().rstrip("=")
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return code_verifier, code_challenge


def _start_callback_server(port: int) -> _CallbackServer:
    server = _CallbackServer(("127.0.0.1", port), _CallbackHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def _exchange_token(token_url: str, payload: dict) -> Optional[dict]:
    try:
        resp = requests.post(token_url, data=payload, timeout=20)
        if resp.status_code in (200, 201):
            return resp.json()
        return None
    except Exception:
        return None


def login_with_oauth(provider_name: str, auth_url: str, token_url: str, client_id: str, redirect_port: int = 53682,
                     scopes: str = "", client_secret: Optional[str] = None, use_pkce: bool = True) -> Optional[dict]:
    # PKCE flow with local callback server. If endpoints do not work or user cancels, return None.
    code_verifier = code_challenge = None
    if use_pkce:
        code_verifier, code_challenge = _generate_pkce_pair()
    redirect_uri = f"http://127.0.0.1:{redirect_port}/callback"

    # Build authorization URL
    state = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scopes,
        "state": state,
    }
    if use_pkce:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"
    query = urllib.parse.urlencode(params, doseq=True)
    authorization_url = f"{auth_url}?{query}"

    # Start local server and open browser
    server = _start_callback_server(redirect_port)
    webbrowser.open(authorization_url)

    # Wait for code (with timeout)
    start = time.time()
    code = None
    while time.time() - start < 300:
        if getattr(server, "code", None):
            code = server.code
            break
        time.sleep(0.5)

    server.shutdown()
    if not code:
        return None

    # Exchange code for token
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
    }
    if code_verifier:
        payload["code_verifier"] = code_verifier
    if client_secret:
        payload["client_secret"] = client_secret

    token_resp = _exchange_token(token_url, payload)
    return token_resp
