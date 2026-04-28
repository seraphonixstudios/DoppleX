import pytest
from src.oauth.oauth_manager import authorize_provider
from src.db.database import SessionLocal
from src.models import Account
from unittest.mock import patch


def test_oauth_authorize_x_stores_tokens(monkeypatch):
    # Remove existing X account if present
    with SessionLocal() as db:
        acc = db.query(Account).filter(Account.platform == "X").first()
        if acc:
            db.delete(acc)
            db.commit()

    mock_token_resp = {
        "access_token": "TEST_X_TOKEN",
        "expires_in": 3600,
        "refresh_token": "TEST_X_REFRESH",
    }

    monkeypatch.setattr("src.oauth.oauth_manager.login_with_oauth", lambda *args, **kwargs: mock_token_resp)
    msg = authorize_provider("X")

    # Validate that account was created and tokens persisted
    with SessionLocal() as db:
        acc = db.query(Account).filter(Account.platform == "X").first()
        assert acc is not None
        assert acc.token_encrypted is not None
        assert acc.refresh_token_encrypted is not None
        assert acc.token_expiry is not None
        # expiry should be roughly now + 3600 seconds; allow a small delta tolerance
        from datetime import datetime, timedelta
        assert isinstance(acc.token_expiry, datetime)
        delta = acc.token_expiry - datetime.utcnow()
    assert timedelta(seconds=3500) < delta < timedelta(seconds=3700)


def test_oauth_refresh_provider_mock(monkeypatch):
    from src.oauth.oauth_manager import refresh_provider
    from src.db.database import SessionLocal, engine, Base
    # Ensure a clean X account exists for refresh
    from src.models import Account  # type: ignore
    with SessionLocal() as db:
        acc = db.query(Account).filter(Account.platform == "X").first()
        if not acc:
            acc = Account(platform="X", username="tester")
            db.add(acc)
            db.commit()
            db.refresh(acc)
    class DummyResp:
        status_code = 200
        def json(self):
            return {
                "access_token": "REFRESHED_TOKEN",
                "expires_in": 3600,
                "refresh_token": "REFRESHED_REFRESH",
            }
        @property
        def text(self):
            return "ok"
    import src.oauth.oauth_manager as om
    monkeypatch.setattr("src.oauth.oauth_manager.requests.post", lambda *args, **kwargs: DummyResp())
    res = refresh_provider("X")
    assert res["ok"] is True
