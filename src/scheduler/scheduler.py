from __future__ import annotations

from datetime import datetime
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

from db.database import SessionLocal
from models import ScheduledPost
from x_api.x_client import post_tweet  # type: ignore
from tiktok.tiktok_client import upload_video  # type: ignore
from encryption.crypto import decrypt, encrypt
from utils.logger import get_logger

logger = get_logger("you2.scheduler")


class You2Scheduler:
    def __init__(self):
        self._scheduler = BackgroundScheduler()
        self._scheduler.start()

    def schedule_post(self, account_id: int, content: str, when: Optional[str] = None):
        if when:
            dt = datetime.fromisoformat(when)
            self._scheduler.add_job(self._publish, DateTrigger(run_date=dt), args=[account_id, content])
        else:
            # Fire immediately as a safeguard
            self._scheduler.add_job(self._publish, DateTrigger(run_date=datetime.utcnow()), args=[account_id, content])

    def _publish(self, account_id: int, content: str):
        # Lightweight, platform-aware publish path (dry-run disabled in Part 2 for live environment)
        with SessionLocal() as db:
            acc = db.query(ScheduledPost).get(account_id)
        # Try to fetch account platform and tokens
        # For demonstration, just log
        logger.info(f"Publish scheduled post for account {account_id}: {content}")
        # Real publishing calls will be wired in Part 2 with proper token usage
