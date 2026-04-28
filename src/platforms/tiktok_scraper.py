from __future__ import annotations
import json
from typing import List, Dict, Any
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

from db.database import SessionLocal
from models import Account, PostHistory, StyleProfile
from encryption.crypto import decrypt
from utils.logger import get_logger

logger = get_logger("you2.tiktok_scraper")

def scrape_tiktok_videos(account_username: str, video_count: int = 50) -> List[Dict[str, Any]]:
    """Scrape real TikTok videos for a user to build style profile."""
    if sync_playwright is None:
        logger.error("Playwright not installed. Run: pip install playwright && python -m playwright install")
        return []

    cookies = None
    with SessionLocal() as db:
        acc = db.query(Account).filter(Account.platform == "TikTok", Account.username == account_username).first()
        if acc and acc.cookies_encrypted:
            try:
                cookies = json.loads(decrypt(acc.cookies_encrypted))
            except Exception as e:
                logger.warning(f"Failed to decrypt TikTok cookies: {e}")

    videos = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            if cookies:
                try:
                    context.add_cookies(cookies)
                except Exception as e:
                    logger.warning(f"Failed to add cookies: {e}")
            page = context.new_page()
            page.goto(f"https://www.tiktok.com/@{account_username}", timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            for _ in range(min(5, (video_count // 10) + 1)):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)

            video_elements = page.query_selector_all("a[href*='/video/']")
            for elem in video_elements[:video_count]:
                href = elem.get_attribute("href")
                if not href or "/video/" not in href:
                    continue
                video_id = href.split("/")[-1].split("?")[0]
                desc = ""
                try:
                    desc_elem = elem.query_selector("[data-e2e='video-desc']") or elem.query_selector(".video-meta-title")
                    if desc_elem:
                        desc = desc_elem.inner_text().strip()
                except Exception:
                    pass
                videos.append({"id": video_id, "url": href, "description": desc, "username": account_username})
                if len(videos) >= video_count:
                    break
            browser.close()

        with SessionLocal() as db:
            acc = db.query(Account).filter(Account.platform == "TikTok", Account.username == account_username).first()
            if not acc:
                acc = Account(platform="TikTok", username=account_username)
                db.add(acc)
                db.commit()
                db.refresh(acc)

            style_profile = db.query(StyleProfile).filter(StyleProfile.account_id == acc.id).first()
            if not style_profile:
                style_profile = StyleProfile(account_id=acc.id, style_data=json.dumps({"platform": "TikTok", "posts": []}))
                db.add(style_profile)

            from datetime import datetime
            new_posts = []
            for v in videos:
                existing = db.query(PostHistory).filter(PostHistory.post_id == v["id"]).first()
                if not existing:
                    ph = PostHistory(
                        account_id=acc.id, platform="TikTok", post_id=v["id"],
                        content=v.get("description", ""), created_at=datetime.utcnow(),
                        metadata=json.dumps({"url": v.get("url", ""), "source": "scraper"})
                    )
                    db.add(ph)
                    new_posts.append(v.get("description", ""))

            if new_posts:
                existing_data = json.loads(style_profile.style_data) if style_profile.style_data else {"posts": []}
                existing_data.setdefault("posts", []).extend(new_posts)
                style_profile.style_data = json.dumps(existing_data)
            db.commit()

        logger.info(f"Scraped {len(videos)} TikTok videos for {account_username}")
        return videos
    except Exception as e:
        logger.exception(f"TikTok scraping failed for {account_username}: {e}")
        return []

if __name__ == "__main__":
    import sys
    username = sys.argv[1] if len(sys.argv) > 1 else "target_username"
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    videos = scrape_tiktok_videos(username, count)
    print(f"Scraped {len(videos)} videos")
