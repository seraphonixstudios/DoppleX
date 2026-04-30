from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

from sqlalchemy import func

from db.database import SessionLocal
from models import PostHistory, Account, AuditLog
from utils.logger import get_logger
from utils.time_utils import utc_now

logger = get_logger("you2.analytics")


def get_post_counts_by_day(days: int = 30) -> List[Tuple[str, int]]:
    with SessionLocal() as db:
        since = utc_now() - timedelta(days=days)
        results = db.query(
            func.date(PostHistory.created_at).label("day"),
            func.count(PostHistory.id).label("count")
        ).filter(
            PostHistory.created_at >= since
        ).group_by("day").order_by("day").all()
        return [(str(r.day), r.count) for r in results]


def get_engagement_summary(account_id: int | None = None) -> Dict:
    with SessionLocal() as db:
        query = db.query(PostHistory).filter(PostHistory.engagement.isnot(None))
        if account_id:
            query = query.filter(PostHistory.account_id == account_id)

        posts = query.all()
        total_likes = 0
        total_replies = 0
        total_retweets = 0
        count = 0

        for p in posts:
            try:
                engagement = json.loads(p.engagement)
                total_likes += engagement.get("like_count", 0)
                total_replies += engagement.get("reply_count", 0)
                total_retweets += engagement.get("retweet_count", 0)
                count += 1
            except Exception:
                pass

        return {
            "total_posts": count,
            "total_likes": total_likes,
            "total_replies": total_replies,
            "total_retweets": total_retweets,
            "avg_likes": round(total_likes / count, 1) if count > 0 else 0,
            "avg_replies": round(total_replies / count, 1) if count > 0 else 0,
            "avg_retweets": round(total_retweets / count, 1) if count > 0 else 0,
        }


def get_platform_breakdown() -> Dict[str, int]:
    with SessionLocal() as db:
        results = db.query(
            PostHistory.platform,
            func.count(PostHistory.id)
        ).group_by(PostHistory.platform).all()
        return {platform: count for platform, count in results}


def get_top_posts(account_id: int | None = None, limit: int = 10) -> List[Dict]:
    with SessionLocal() as db:
        query = db.query(PostHistory).filter(PostHistory.engagement.isnot(None))
        if account_id:
            query = query.filter(PostHistory.account_id == account_id)

        posts = query.all()
        scored = []
        for p in posts:
            try:
                engagement = json.loads(p.engagement)
                score = (
                    engagement.get("like_count", 0) +
                    engagement.get("reply_count", 0) * 2 +
                    engagement.get("retweet_count", 0) * 3
                )
                scored.append((score, p))
            except Exception:
                pass

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "content": p.content[:100],
                "score": score,
                "platform": p.platform,
                "posted_at": p.posted_at,
            }
            for score, p in scored[:limit]
        ]


def get_source_breakdown() -> Dict[str, int]:
    with SessionLocal() as db:
        results = db.query(
            PostHistory.source,
            func.count(PostHistory.id)
        ).group_by(PostHistory.source).all()
        return {source: count for source, count in results}


def get_activity_heatmap(hours: int = 168) -> Dict[int, int]:  # 7 days * 24 hours
    """Return posts per hour of day (0-23)."""
    with SessionLocal() as db:
        since = utc_now() - timedelta(hours=hours)
        posts = db.query(PostHistory).filter(
            PostHistory.posted_at >= since
        ).all()

        heatmap = defaultdict(int)
        for p in posts:
            if p.posted_at:
                heatmap[p.posted_at.hour] += 1
        return dict(heatmap)
