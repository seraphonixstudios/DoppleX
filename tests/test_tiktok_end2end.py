import types
import pytest


@pytest.mark.asyncio
async def test_tiktok_live_flow_mock(monkeypatch):
    # Import the function to test and then patch the underlying implementation to simulate success
    from tiktok.tiktok_client import upload_video as real_upload

    async def mock_upload(account_id, path, cap, hashtags=None, dry_run=False):
        return {"ok": True, "info": "mock"}

    # Patch the actual upload_video to simulate a successful upload
    monkeypatch.setattr(
        'tiktok.tiktok_client.upload_video',
        mock_upload
    )
    res = await real_upload(1, "path/to/video.mp4", "caption", dry_run=True)
    assert isinstance(res, dict)
