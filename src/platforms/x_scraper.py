from __future__ import annotations

import json
from typing import Dict, List, Optional
from datetime import datetime

from encryption.crypto import decrypt
from models import Account, PostHistory
from db.database import SessionLocal
from x_api.x_client import XClient
from utils.logger import get_logger
from utils.audit import log_action

logger = get_logger("you2.x_scraper")


def scrape_x_history(account_id: int, max_results: int = 100) -> Dict:
    from x_api.x_client import fetch_user_history
    return fetch_user_history(account_id, max_results)
