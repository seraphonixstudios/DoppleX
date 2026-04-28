from __future__ import annotations
import os
import json
from typing import List, Dict, Any
from datetime import datetime

try:
    import tweepy
except ImportError:
    tweepy = None

from db.database import SessionLocal
from models import Account, PostHistory, StyleProfile
from encryption.crypto import decrypt
from utils.logger import get_logger

logger = get_logger("you2.x_scraper")

def scrape_x_posts(username: str, count: int = 200) -> List[Dict[str, Any]]:
    """Scrape real posts from X (Twitter) using API v2 via tweepy."""
    if tweepy is None:
        logger.error("tweepy not installed. Run: pip install tweepy")
        return []

    api_key = os.environ.get("YOU2_X_SCRAPE_API_KEY")
    api_secret = os.environ.get("YOU2_X_SCRAPE_API_SECRET")
    access_token = os.environ.get("YOU2_X_SCRAPE_ACCESS_TOKEN")
    access_secret = os.environ.get("YOU2_X_SCRAPE_ACCESS_SECRET")

    if not all([api_key, api_secret, access_token, access_secret]):
        logger.error("Missing X API credentials. Set YOU2_X_SCRAPE_* environment variables.")
        return []

    try:
        auth = tweepy.OAuth1(api_key, api_secret, access_token, access_secret)
        api = tweepy.API(auth, wait_on_rate_limit=True)

        posts = []
        for status in tweepy.Cursor(api.user_timeline, screen_name=username, count=min(count, 200), tweet_mode="extended").items(count):
            posts.append({
                "id": str(status.id),
                "text": status.full_text if hasattr(status, 'full_text') else status.text,
                "created_at": status.created_at.isoformat(),
                "retweet_count": status.retweet_count,
                "favorite_count": status.favorite_count,
                "is_retweet": hasattr(status, 'retweeted_status'),
            })

        with SessionLocal() as db:
            acc = db.query(Account).filter(Account.platform == "X", Account.username == username).first()
            if not acc:
                acc = Account(platform="X", username=username)
                db.add(acc)
                db.commit()
                db.refresh(acc)

            style_profile = db.query(StyleProfile).filter(StyleProfile.account_id == acc.id).first()
            if not style_profile:
                style_profile = StyleProfile(account_id=acc.id, style_data=json.dumps({"platform": "X", "posts": []}))
                db.add(style_profile)

            new_posts = []
            for p in posts:
                existing = db.query(PostHistory).filter(PostHistory.post_id == p["id"]).first()
                if not existing:
                    ph = PostHistory(
                        account_id=acc.id, platform="X", post_id=p["id"],
                        content=p["text"], created_at=datetime.fromisoformat(p["created_at"]),
                        metadata=json.dumps({
                            "retweets": p["retweet_count"],
                            "likes": p["favorite_count"],
                            "is_retweet": p["is_retweet"],
                        })
                    )
                    db.add(ph)
                    new_posts.append(p["text"])

            if new_posts:
                existing_data = json.loads(style_profile.style_data) if style_profile.style_data else {"posts": []}
                existing_data.setdefault("posts", []).extend(new_posts)
                style_profile.style_data = json.dumps(existing_data)
            db.commit()

        logger.info(f"Scraped {len(posts)} posts from X for {username}")
        return posts
    except Exception as e:
        logger.exception(f"X scraping failed for {username}: {e}")
        return []

if __name__ == "__main__":
    import sys
    username = sys.argv[1] if len(sys.argv) > 1 else "your_username"
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    posts = scrape_x_posts(username, count)
    print(f"Scraped {len(posts)} posts")
