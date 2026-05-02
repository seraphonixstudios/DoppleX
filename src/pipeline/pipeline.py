from __future__ import annotations

import asyncio
import json
import random
import threading
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

from db.database import SessionLocal
from models import Account, PostHistory, StyleProfile, ScheduledPost, ContentQueue
from brain.generator import ContentGenerator
from brain.style_learner import StyleLearner
from platforms.x_scraper import scrape_x_history
from platforms.tiktok_scraper import scrape_tiktok_history
from x_api.x_client import post_tweet
from tiktok.tiktok_client import upload_video
from scheduler.scheduler import You2Scheduler
from analytics import metrics
from utils.logger import get_logger
from utils.audit import log_action
from utils.time_utils import utc_now
from utils.error_handler import ErrorContext, log_exception
from config.settings import load_settings

logger = get_logger("you2.pipeline")
settings = load_settings()


class PipelineEngine:
    """Full pipeline engine for content generation, queueing, and publishing."""

    def __init__(self):
        self.generator = ContentGenerator()
        self.scheduler = You2Scheduler()
        self.style_learner = StyleLearner()
        self._worker_thread: Optional[threading.Thread] = None
        self._worker_running = False

    # ───────────────────────── Queue Management ─────────────────────────

    def queue_content(
        self,
        account_id: int,
        content: str,
        platform: str = "X",
        media_path: Optional[str] = None,
        priority: int = 5,
        scheduled_at: Optional[datetime] = None,
        topic_hint: str = "",
        mood: str = "",
        status: str = "draft",
    ) -> ContentQueue:
        """Add content to the queue."""
        with ErrorContext("queue_content", account_id=account_id, platform=platform):
            with SessionLocal() as db:
                item = ContentQueue(
                    account_id=account_id,
                    content=content,
                    platform=platform,
                    media_path=media_path,
                    priority=priority,
                    scheduled_at=scheduled_at,
                    topic_hint=topic_hint,
                    mood=mood,
                    status=status,
                )
                db.add(item)
                db.commit()
                db.refresh(item)
                log_action("content_queued", account_id=account_id, status="success", details=f"platform={platform}, priority={priority}")
                return item

    def approve_content(self, queue_id: int) -> bool:
        """Move content from draft to approved."""
        with ErrorContext("approve_content", queue_id=queue_id):
            with SessionLocal() as db:
                item = db.get(ContentQueue, queue_id)
                if not item or item.status not in ("draft", "failed"):
                    return False
                item.status = "approved"
                db.commit()
                log_action("content_approved", account_id=item.account_id, status="success")
                return True

    async def publish_queued(self, queue_id: int) -> Dict:
        """Publish a queued item immediately."""
        with ErrorContext("publish_queued", queue_id=queue_id):
            with SessionLocal() as db:
                item = db.get(ContentQueue, queue_id)
                if not item:
                    return {"ok": False, "error": "Queue item not found"}

                account = db.get(Account, item.account_id)
                if not account or not account.is_active:
                    item.status = "failed"
                    item.error_message = "Account not found or inactive"
                    db.commit()
                    return {"ok": False, "error": "Account not found or inactive"}

                result = await self._publish_to_platform(account, item)

                if result.get("ok"):
                    item.status = "published"
                    item.retry_count = 0
                else:
                    item.retry_count += 1
                    item.error_message = result.get("error", "Unknown error")
                    if item.retry_count >= item.max_retries:
                        item.status = "failed"
                    else:
                        item.status = "queued"  # Will retry later
                db.commit()
                return result

    async def _publish_to_platform(self, account: Account, item: ContentQueue) -> Dict:
        """Publish to the appropriate platform(s)."""
        if settings.use_dry_run:
            logger.info("[DRY RUN] Would publish to %s: %s", item.platform, item.content[:80])
            return {"ok": True, "dry_run": True}

        if item.platform == "cross":
            # Cross-post to both X and TikTok
            x_result = await post_tweet(account.id, item.content) if account.platform == "X" else {"ok": False, "error": "Not an X account"}
            tiktok_result = await upload_video(account.id, item.media_path or "", item.content) if account.platform == "TikTok" else {"ok": False, "error": "Not a TikTok account"}
            # If we have a cross-post setup, we'd need two accounts. For now, return whichever succeeded.
            if x_result.get("ok"):
                return x_result
            return tiktok_result

        if item.platform == "X":
            return await post_tweet(account.id, item.content)
        elif item.platform == "TikTok":
            if not item.media_path:
                return {"ok": False, "error": "TikTok posts require a video file"}
            return await upload_video(account.id, item.media_path, item.content)

        return {"ok": False, "error": f"Unknown platform: {item.platform}"}

    def list_queue(
        self,
        account_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[ContentQueue]:
        """List queue items."""
        with SessionLocal() as db:
            query = db.query(ContentQueue).order_by(ContentQueue.priority, ContentQueue.created_at)
            if account_id:
                query = query.filter(ContentQueue.account_id == account_id)
            if status:
                query = query.filter(ContentQueue.status == status)
            return query.limit(limit).all()

    def delete_queue_item(self, queue_id: int) -> bool:
        """Remove an item from the queue."""
        with SessionLocal() as db:
            item = db.get(ContentQueue, queue_id)
            if not item:
                return False
            db.delete(item)
            db.commit()
            return True

    # ───────────────────────── Bulk Generation ─────────────────────────

    async def bulk_generate(
        self,
        account_id: int,
        topics: List[str],
        moods: Optional[List[str]] = None,
        count_per_topic: int = 1,
        auto_queue: bool = True,
        platform: str = "X",
    ) -> List[ContentQueue]:
        """Generate multiple posts across topics and add to queue."""
        with ErrorContext("bulk_generate", account_id=account_id, topic_count=len(topics)):
            if moods is None:
                moods = ["", "excited", "thoughtful", "casual"]

            created_items = []
            for topic in topics:
                for _ in range(count_per_topic):
                    mood = random.choice(moods)
                    try:
                        content = await self.generator.generate_and_store(
                            account_id,
                            topic_hint=topic,
                            mood=mood,
                        )
                        if auto_queue:
                            item = self.queue_content(
                                account_id=account_id,
                                content=content,
                                platform=platform,
                                topic_hint=topic,
                                mood=mood,
                                status="draft",
                            )
                            created_items.append(item)
                    except Exception as e:
                        log_exception("Bulk generation failed for topic", e, account_id=account_id, topic=topic)

            log_action("bulk_generated", account_id=account_id, status="success", details=f"items={len(created_items)}")
            return created_items

    # ───────────────────────── Auto-Retry ─────────────────────────

    def retry_failed(self, account_id: Optional[int] = None, max_age_hours: int = 24) -> int:
        """Retry failed queue items and scheduled posts. Returns retry count."""
        retry_count = 0
        cutoff = utc_now() - timedelta(hours=max_age_hours)

        with SessionLocal() as db:
            # Retry failed scheduled posts
            query = db.query(ScheduledPost).filter(
                ScheduledPost.status == "failed",
                ScheduledPost.scheduled_at >= cutoff,
            )
            if account_id:
                query = query.filter(ScheduledPost.account_id == account_id)
            failed_posts = query.all()

            for post in failed_posts:
                # Reschedule for 5 minutes from now
                post.scheduled_at = utc_now() + timedelta(minutes=5)
                post.status = "scheduled"
                post.error_message = None
                self.scheduler._schedule_job(post)
                retry_count += 1
                log_action("scheduled_retry", account_id=post.account_id, status="success", details=f"post_id={post.id}")

            db.commit()

        # Retry failed queue items
        with SessionLocal() as db:
            query = db.query(ContentQueue).filter(
                ContentQueue.status == "failed",
                ContentQueue.retry_count < ContentQueue.max_retries,
                ContentQueue.updated_at >= cutoff,
            )
            if account_id:
                query = query.filter(ContentQueue.account_id == account_id)
            failed_items = query.all()

            for item in failed_items:
                item.status = "queued"
                retry_count += 1
                log_action("queue_retry", account_id=item.account_id, status="success", details=f"queue_id={item.id}")

            db.commit()

        logger.info("Retried %d failed items", retry_count)
        return retry_count

    # ───────────────────────── Best Time Detection ─────────────────────────

    def get_best_posting_times(self, account_id: Optional[int] = None) -> List[Tuple[int, int]]:
        """Return top 3 hours of day (0-23) with highest engagement, paired with average score."""
        heatmap = metrics.get_activity_heatmap(hours=168 * 4)  # ~4 weeks
        if not heatmap:
            return [(9, 0), (14, 0), (19, 0)]  # Defaults

        # Score by post count + engagement
        scored_hours = []
        for hour, count in heatmap.items():
            scored_hours.append((hour, count))

        scored_hours.sort(key=lambda x: x[1], reverse=True)
        return scored_hours[:3]

    def schedule_at_best_time(
        self,
        account_id: int,
        content: str,
        day_offset: int = 1,
        media_path: Optional[str] = None,
    ) -> ScheduledPost:
        """Schedule a post for the next best time slot."""
        best_times = self.get_best_posting_times(account_id)
        target_hour = best_times[0][0] if best_times else 14

        target_day = utc_now().date() + timedelta(days=day_offset)
        scheduled_dt = datetime.combine(target_day, datetime.min.time()) + timedelta(hours=target_hour)

        if scheduled_dt < utc_now():
            scheduled_dt += timedelta(days=1)

        return self.scheduler.schedule_post(account_id, content, scheduled_dt, media_path=media_path)

    # ───────────────────────── Scrape → Generate Pipeline ─────────────────────────

    async def scrape_and_generate(
        self,
        account_id: int,
        topic: str = "",
        mood: str = "",
        auto_queue: bool = True,
    ) -> Dict:
        """Full pipeline: scrape history → analyze style → generate content → queue."""
        with ErrorContext("scrape_and_generate", account_id=account_id, topic=topic, mood=mood):
            with SessionLocal() as db:
                account = db.get(Account, account_id)
                if not account:
                    return {"ok": False, "error": "Account not found"}

            results = {"scraped": 0, "analyzed": False, "generated": False, "queued": False}

            # 1. Scrape history
            if account.platform == "X":
                scrape_result = await scrape_x_history(account_id, max_results=50)
            elif account.platform == "TikTok":
                scrape_result = await scrape_tiktok_history(account_id, max_videos=30)
            else:
                return {"ok": False, "error": "Unknown platform"}

            if scrape_result.get("ok"):
                results["scraped"] = scrape_result.get("imported", 0)

            # 2. Analyze style
            try:
                profile = await self.style_learner.analyze_account(account_id)
                results["analyzed"] = True
            except Exception as e:
                log_exception("Style analysis failed in pipeline", e, account_id=account_id)

            # 3. Generate content
            try:
                content = await self.generator.generate_and_store(
                    account_id,
                    topic_hint=topic,
                    mood=mood,
                )
                results["generated"] = True
                results["content"] = content
            except Exception as e:
                log_exception("Generation failed in pipeline", e, account_id=account_id)
                return {**results, "ok": False, "error": str(e)}

            # 4. Queue
            if auto_queue:
                item = self.queue_content(
                    account_id=account_id,
                    content=content,
                    platform=account.platform,
                    topic_hint=topic,
                    mood=mood,
                    status="draft",
                )
                results["queued"] = True
                results["queue_id"] = item.id

            log_action("scrape_generate_pipeline", account_id=account_id, status="success")
            return {**results, "ok": True}

    # ───────────────────────── Queue Worker ─────────────────────────

    def start_worker(self, interval_seconds: int = 60):
        """Start background worker that processes approved queue items."""
        if self._worker_running:
            return
        self._worker_running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, args=(interval_seconds,), daemon=True)
        self._worker_thread.start()
        logger.info("Pipeline worker started (interval=%ds)", interval_seconds)

    def stop_worker(self):
        """Stop the background worker."""
        self._worker_running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
        logger.info("Pipeline worker stopped")

    def _worker_loop(self, interval_seconds: int):
        """Background loop: process approved items and retry failures."""
        while self._worker_running:
            try:
                asyncio.run(self._process_approved_items())
                self.retry_failed(max_age_hours=24)
            except Exception as e:
                log_exception("Pipeline worker error", e)
            time.sleep(interval_seconds)

    async def _process_approved_items(self, batch_size: int = 5):
        """Publish approved items that are due."""
        with SessionLocal() as db:
            items = db.query(ContentQueue).filter(
                ContentQueue.status == "approved",
            ).order_by(ContentQueue.priority, ContentQueue.created_at).limit(batch_size).all()

            for item in items:
                if item.scheduled_at and item.scheduled_at > utc_now():
                    continue

                item.status = "queued"
                db.commit()

                result = await self.publish_queued(item.id)
                if not result.get("ok") and not result.get("dry_run"):
                    logger.warning("Queue publish failed for item %d: %s", item.id, result.get("error"))

    # ───────────────────────── Cross-Post ─────────────────────────

    async def cross_post(
        self,
        x_account_id: int,
        tiktok_account_id: int,
        content: str,
        video_path: Optional[str] = None,
        schedule_at: Optional[datetime] = None,
    ) -> Dict:
        """Create linked posts for X (text) and TikTok (video + caption)."""
        with ErrorContext("cross_post", account_id=x_account_id, tiktok_account_id=tiktok_account_id):
            results = {"x": None, "tiktok": None}

            if schedule_at:
                # Schedule both
                x_post = self.scheduler.schedule_post(x_account_id, content, schedule_at)
                tiktok_post = self.scheduler.schedule_post(
                    tiktok_account_id, content, schedule_at, media_path=video_path
                )
                results["x"] = {"ok": True, "scheduled_id": x_post.id}
                results["tiktok"] = {"ok": True, "scheduled_id": tiktok_post.id}
            else:
                # Post immediately
                if not settings.use_dry_run:
                    results["x"] = await post_tweet(x_account_id, content)
                    if video_path:
                        results["tiktok"] = await upload_video(tiktok_account_id, video_path, content)
                else:
                    results["x"] = {"ok": True, "dry_run": True}
                    results["tiktok"] = {"ok": True, "dry_run": True}

            log_action("cross_post", account_id=x_account_id, status="success", details=f"tiktok_account={tiktok_account_id}")
            return results

    def shutdown(self):
        """Clean shutdown of pipeline engine."""
        self.stop_worker()
        self.scheduler.shutdown()
