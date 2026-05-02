from __future__ import annotations

from typing import Dict

from models import Account
from tiktok.tiktok_client import upload_video as _upload_video
from utils.logger import get_logger

logger = get_logger("you2.tiktok_poster")


async def post_video(account: Account, video_path: str, caption: str, hashtags=None) -> dict:
    return await _upload_video(account.id, video_path, caption, hashtags or [])
