from __future__ import annotations

from typing import Dict

from models import Account
from tiktok.tiktok_client import TikTokClient
from utils.logger import get_logger

logger = get_logger("you2.tiktok_poster")


def post_video(account: Account, video_path: str, caption: str, hashtags=None) -> dict:
    client = TikTokClient(account)
    return client.upload_video(video_path, caption, hashtags or [])
