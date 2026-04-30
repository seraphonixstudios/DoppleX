import pytest
from tiktok.tiktok_client import upload_video


def test_tiktok_upload_dry_run():
    result = upload_video(1, "/path/to/video.mp4", "caption", dry_run=True)
    assert isinstance(result, dict)
    assert result.get("ok") is True
