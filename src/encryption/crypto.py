from __future__ import annotations

import base64
import os
try:
    import keyring  # type: ignore
    KEYRING_AVAILABLE = True
except Exception:
    KEYRING_AVAILABLE = False

from cryptography.fernet import Fernet

_KEY_SERVICE = "you2"
_KEY_NAME = "master-key"


def _load_or_create_key() -> bytes:
    # Try keyring first for cross-platform secure storage
    if KEYRING_AVAILABLE:
        existing = keyring.get_password(_KEY_SERVICE, _KEY_NAME)
        if existing:
            return existing.encode()
        # generate and store
        key = Fernet.generate_key()
        keyring.set_password(_KEY_SERVICE, _KEY_NAME, key.decode())
        return key
    # Fallback to local file in repo (less ideal, but functional for offline use)
    key_path = os.path.join(os.path.dirname(__file__), "..", "you2.key")
    key_path = os.path.abspath(key_path)
    if os.path.exists(key_path):
        with open(key_path, "rb") as f:
            return f.read()
    key = Fernet.generate_key()
    os.makedirs(os.path.dirname(key_path), exist_ok=True)
    with open(key_path, "wb") as f:
        f.write(key)
    return key


_FERNET_KEY = _load_or_create_key()
_FERNET = Fernet(_FERNET_KEY)


def encrypt(plaintext: str) -> str:
    if plaintext is None:
        return None
    return _FERNET.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    if ciphertext is None:
        return None
    return _FERNET.decrypt(ciphertext.encode()).decode()
