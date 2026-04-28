from __future__ import annotations

import os
try:
    import keyring  # type: ignore
    KEYRING_AVAILABLE = True
except Exception:
    KEYRING_AVAILABLE = False

def _os_path(provider: str, token_type: str) -> str:
    home = os.path.expanduser("~")
    base = os.path.join(home, ".you2", "tokens")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, f"{provider}_{token_type}.tok")


def store_token(provider: str, token_type: str, token: str) -> None:
    service = f"you2.{provider}"
    if KEYRING_AVAILABLE:
        try:
            keyring.set_password(service, token_type, token)
            return
        except Exception:
            pass
    path = _os_path(provider, token_type)
    with open(path, "w", encoding="utf-8") as f:
        f.write(token)


def load_token(provider: str, token_type: str) -> str | None:
    service = f"you2.{provider}"
    if KEYRING_AVAILABLE:
        try:
            return keyring.get_password(service, token_type)  # type: ignore
        except Exception:
            pass
    path = _os_path(provider, token_type)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return None
