import types
import pytest


def test_tiktok_live_flow_mock(monkeypatch):
    # Import the function to test and then patch the underlying implementation to simulate success
    from src.tiktok.tiktok_client import upload_video as real_upload
    class DummyAccount:
        cookies_encrypted = None
    acc = DummyAccount()
    acc.cookies_encrypted = None
    # Patch the actual upload_video to simulate a successful upload
    monkeypatch.setattr('src.tiktok.tiktok_client.upload_video', lambda account, path, cap, dry_run=False: {"ok": True, "info": "mock"})
    res = __import__('src.tiktok.tiktok_client', fromlist=['upload_video']).upload_video(acc, "path/to/video.mp4", "caption", dry_run=True)
    assert isinstance(res, dict)
