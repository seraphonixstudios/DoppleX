from __future__ import annotations

from tiktok.tiktok_client import upload_video
from models import Account


def post_video(account: Account, video_path: str, caption: str) -> dict:
    return upload_video(account, video_path, caption)
