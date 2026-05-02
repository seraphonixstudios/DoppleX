from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

from db.database import SessionLocal
from models import ScheduledPost, Account
from x_api.x_client import post_tweet
from tiktok.tiktok_client import upload_video
from platforms.x_reply_bot import XReplyBot
from encryption.crypto import decrypt
from utils.logger import get_logger
from utils.audit import log_action
from utils.time_utils import utc_now
from utils.error_handler import ErrorContext, log_exception, notify_error
from config.settings import load_settings

logger = get_logger("you2.scheduler")
settings = load_settings()


class You2Scheduler:
    def __init__(self):
        self._scheduler = BackgroundScheduler(timezone=settings.scheduler_timezone)
        self._scheduler.add_listener(self._on_job_event, EVENT_JOB_ERROR | EVENT_JOB_EXECUTED)
        self._scheduler.start()
        self._load_pending_jobs()

    def _load_pending_jobs(self):
        with SessionLocal() as db:
            pending = db.query(ScheduledPost).filter(
                ScheduledPost.status == "scheduled",
                ScheduledPost.scheduled_at > utc_now()
            ).all()
            for post in pending:
                self._schedule_job(post)
            logger.info("Loaded %d pending scheduled posts", len(pending))

    def _on_job_event(self, event):
        if event.exception:
            logger.error("Scheduled job %s failed: %s", event.job_id, event.exception)
        else:
            logger.info("Scheduled job %s executed successfully", event.job_id)

    def _schedule_job(self, scheduled_post: ScheduledPost):
        job_id = f"post_{scheduled_post.id}"
        # Remove existing job if present
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass

        self._scheduler.add_job(
            self._publish_sync_wrapper,
            DateTrigger(run_date=scheduled_post.scheduled_at),
            id=job_id,
            args=[scheduled_post.id],
            replace_existing=True,
        )
        logger.info("Scheduled post %d for %s", scheduled_post.id, scheduled_post.scheduled_at)

    def schedule_post(self, account_id: int, content: str, scheduled_at: datetime, media_path: Optional[str] = None) -> ScheduledPost:
        with SessionLocal() as db:
            post = ScheduledPost(
                account_id=account_id,
                content=content,
                media_path=media_path,
                scheduled_at=scheduled_at,
                status="scheduled",
            )
            db.add(post)
            db.commit()
            db.refresh(post)
            self._schedule_job(post)
            log_action("post_scheduled", account_id=account_id, status="success", details=f"scheduled_at={scheduled_at}")
            return post

    def cancel_post(self, post_id: int) -> bool:
        with SessionLocal() as db:
            post = db.get(ScheduledPost, post_id)
            if not post or post.status != "scheduled":
                return False
            account_id = post.account_id
            post.status = "cancelled"
            db.commit()

        try:
            self._scheduler.remove_job(f"post_{post_id}")
        except Exception:
            pass

        log_action("post_cancelled", account_id=account_id, status="success")
        return True

    def _publish_sync_wrapper(self, scheduled_post_id: int):
        """Sync wrapper for APScheduler threads to run async publish."""
        try:
            asyncio.run(self._publish(scheduled_post_id))
        except Exception as e:
            log_exception("Scheduled publish wrapper failed", e, post_id=scheduled_post_id)

    async def _publish(self, scheduled_post_id: int):
        with SessionLocal() as db:
            post = db.get(ScheduledPost, scheduled_post_id)
            if not post or post.status != "scheduled":
                return

            account = db.get(Account, post.account_id)
            if not account or not account.is_active:
                post.status = "failed"
                post.error_message = "Account not found or inactive"
                db.commit()
                return

            with ErrorContext("scheduler_publish", account_id=account.id, platform=account.platform, post_id=scheduled_post_id):
                try:
                    if account.platform == "X":
                        result = await post_tweet(account.id, post.content)
                    elif account.platform == "TikTok":
                        if post.media_path:
                            result = await upload_video(account.id, post.media_path, post.content)
                        else:
                            result = {"ok": False, "error": "TikTok posts require a video file"}
                    else:
                        result = {"ok": False, "error": f"Unknown platform: {account.platform}"}

                    if result.get("ok"):
                        post.status = "published"
                        post.published_at = utc_now()
                        post.post_id = result.get("tweet_id") or result.get("post_id")
                        log_action("scheduled_published", account_id=account.id, status="success", platform=account.platform)
                    else:
                        post.status = "failed"
                        post.error_message = result.get("error", "Unknown error")
                        log_action("scheduled_published", account_id=account.id, status="failed", platform=account.platform, details=result.get("error"))

                    db.commit()
                except Exception as e:
                    log_exception("Scheduled publish failed", e, account_id=account.id, post_id=scheduled_post_id)
                    post.status = "failed"
                    post.error_message = str(e)
                    db.commit()
                    log_action("scheduled_published", account_id=account.id, status="failed", platform=account.platform, details=str(e))

    def get_upcoming_posts(self, account_id: Optional[int] = None, limit: int = 50) -> list:
        with SessionLocal() as db:
            query = db.query(ScheduledPost).filter(
                ScheduledPost.status == "scheduled"
            ).order_by(ScheduledPost.scheduled_at)
            if account_id:
                query = query.filter(ScheduledPost.account_id == account_id)
            return query.limit(limit).all()

    def start_reply_bot(self, account_id: int, interval_minutes: int = 15):
        job_id = f"reply_bot_{account_id}"
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass

        self._scheduler.add_job(
            self._check_replies_sync_wrapper,
            "interval",
            minutes=interval_minutes,
            id=job_id,
            args=[account_id],
            replace_existing=True,
        )
        logger.info("Reply bot started for account %d (every %d min)", account_id, interval_minutes)

    def stop_reply_bot(self, account_id: int):
        job_id = f"reply_bot_{account_id}"
        try:
            self._scheduler.remove_job(job_id)
            logger.info("Reply bot stopped for account %d", account_id)
        except Exception:
            pass

    def _check_replies_sync_wrapper(self, account_id: int):
        """Sync wrapper for APScheduler threads to run async reply check."""
        try:
            asyncio.run(self._check_replies(account_id))
        except Exception as e:
            log_exception("Reply bot wrapper failed", e, account_id=account_id)

    async def _check_replies(self, account_id: int):
        with SessionLocal() as db:
            account = db.get(Account, account_id)
        if not account or not account.reply_bot_enabled:
            return
        with ErrorContext("reply_bot_check", account_id=account_id):
            try:
                bot = XReplyBot(account)
                result = await bot.run_once()
                if result.get("replied", 0) > 0:
                    logger.info("Reply bot: %d replies sent for account %d", result["replied"], account_id)
            except Exception as e:
                log_exception("Reply bot check failed", e, account_id=account_id)

    def shutdown(self):
        self._scheduler.shutdown(wait=True)
        logger.info("Scheduler shut down")
