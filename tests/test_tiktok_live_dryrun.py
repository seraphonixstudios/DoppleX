import pytest
from src.tiktok.tiktok_client import upload_video


class DummyAccount:
    cookies_encrypted = None

def test_tiktok_upload_dry_run(monkeypatch):
    dummy = DummyAccount()
    result = upload_video(dummy, "/path/to/video.mp4", "caption", dry_run=True)
    assert isinstance(result, dict)
    assert result.get("ok") is True
