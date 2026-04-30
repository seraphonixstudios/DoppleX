from __future__ import annotations

import json
from typing import Dict

from models import Account
from tiktok.tiktok_client import scrape_tiktok_history
from utils.logger import get_logger

logger = get_logger("you2.tiktok_scraper")


def scrape_tiktok_history(account_id: int, max_videos: int = 50) -> Dict:
    return scrape_tiktok_history(account_id, max_videos)
