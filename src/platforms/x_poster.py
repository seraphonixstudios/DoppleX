from __future__ import annotations

import json
from typing import Dict, Optional

from encryption.crypto import decrypt
from models import Account
from x_api.x_client import XClient
from utils.logger import get_logger

logger = get_logger("you2.x_poster")


async def post_text(account: Account, content: str, reply_to: str | None = None) -> dict:
    client = XClient(account)
    return await client.post_tweet(content, reply_to=reply_to)
