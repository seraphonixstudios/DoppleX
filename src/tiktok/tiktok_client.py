from __future__ import annotations

import json
import time
import logging
from pathlib import Path
from typing import Optional, Dict, List

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except Exception:
    sync_playwright = None  # type: ignore
    PlaywrightTimeout = Exception  # type: ignore

from encryption.crypto import decrypt
from models import Account, PostHistory
from db.database import SessionLocal
from utils.logger import get_logger
from utils.audit import log_action
from utils.time_utils import utc_now
from config.settings import load_settings

logger = get_logger("you2.tiktok")
settings = load_settings()


class TikTokClient:
    def __init__(self, account: Account):
        self.account = account
        self.cookies = self._load_cookies()

    def _load_cookies(self) -> Optional[List[Dict]]:
        if not self.account.cookies_encrypted:
            return None
        try:
            cookies_json = decrypt(self.account.cookies_encrypted)
            return json.loads(cookies_json)
        except Exception as e:
            logger.error("Failed to load TikTok cookies: %s", e)
            return None

    def upload_video(self, video_path: str, caption: str, hashtags: List[str] | None = None, dry_run: bool = False) -> Dict:
        if dry_run:
            return {"ok": True, "info": "dry_run"}
        if sync_playwright is None:
            return {"ok": False, "error": "Playwright not installed. Run: playwright install"}

        if not self.cookies:
            return {"ok": False, "error": "No cookies available. Please add TikTok session cookies."}

        video_path = Path(video_path)
        if not video_path.exists():
            return {"ok": False, "error": f"Video not found: {video_path}"}

        full_caption = caption
        if hashtags:
            full_caption += " " + " ".join([f"#{tag}" for tag in hashtags])

        for attempt in range(1, settings.max_retries + 1):
            browser = None
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(
                        viewport={"width": 1280, "height": 720},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    )
                    page = context.new_page()

                    # Load cookies before navigation
                    try:
                        context.add_cookies(self.cookies)
                    except Exception as e:
                        logger.warning("Cookie load warning: %s", e)

                    page.goto("https://www.tiktok.com/upload", timeout=60000)
                    page.wait_for_timeout(3000)

                    # Handle file upload
                    file_input = page.locator("input[type='file']").first
                    file_input.wait_for(timeout=15000)
                    file_input.set_input_files(str(video_path.resolve()))

                    # Wait for upload to process
                    page.wait_for_timeout(5000)

                    # Fill caption
                    try:
                        caption_editor = page.locator('[contenteditable="true"]').first
                        caption_editor.wait_for(timeout=15000)
                        caption_editor.fill(full_caption)
                    except Exception:
                        # Fallback: try textarea
                        try:
                            textarea = page.locator("textarea").first
                            textarea.wait_for(timeout=10000)
                            textarea.fill(full_caption)
                        except Exception as e:
                            logger.warning("Caption input fallback failed: %s", e)

                    # Wait for upload processing
                    page.wait_for_timeout(3000)

                    # Click post button
                    post_btn = (
                        page.locator("button:has-text('Post')").first
                        or page.locator("button:has-text('Publish')").first
                        or page.locator("[data-e2e='post_video_button']").first
                    )
                    post_btn.wait_for(timeout=15000)
                    post_btn.click()

                    # Wait for confirmation
                    page.wait_for_timeout(8000)

                    # Check for success indicators
                    url = page.url
                    if "/video/" in url or page.locator("text=Your videos").count() > 0:
                        browser.close()
                        return {"ok": True, "info": f"Upload completed on attempt {attempt}", "url": url}

                    browser.close()
                    return {"ok": True, "info": f"Upload attempt {attempt} completed"}

            except Exception as e:
                logger.warning("TikTok upload attempt %d failed: %s", attempt, e)
                if browser:
                    try:
                        browser.close()
                    except Exception:
                        pass
                time.sleep(2 ** attempt)  # Exponential backoff
                continue

        return {"ok": False, "error": f"TikTok upload failed after {settings.max_retries} retries"}

    def get_user_videos(self, username: str, max_videos: int = 50) -> List[Dict]:
        if sync_playwright is None:
            logger.error("Playwright not installed")
            return []

        videos = []
        browser = None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
                page = context.new_page()

                if self.cookies:
                    try:
                        context.add_cookies(self.cookies)
                    except Exception:
                        pass

                page.goto(f"https://www.tiktok.com/@{username}", timeout=60000)
                page.wait_for_timeout(3000)

                # Scroll to load videos
                for _ in range(min(max_videos // 6, 20)):
                    page.evaluate("window.scrollBy(0, 800)")
                    page.wait_for_timeout(1000)

                # Extract video links and captions
                links = page.locator("a[href*='/video/']").all()
                seen = set()
                for link in links:
                    href = link.get_attribute("href")
                    if href and href not in seen:
                        seen.add(href)
                        videos.append({
                            "url": href,
                            "caption": link.inner_text()[:200],
                        })

                browser.close()
        except Exception as e:
            logger.exception("TikTok scraping failed")
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass

        return videos[:max_videos]


def upload_video(account_id: int, video_path: str, caption: str, hashtags: List[str] | None = None, dry_run: bool = False) -> Dict:
    if dry_run:
        return {"ok": True, "info": "dry_run"}
    with SessionLocal() as db:
        account = db.get(Account, account_id)
        if not account:
            return {"ok": False, "error": "Account not found"}

        client = TikTokClient(account)
        result = client.upload_video(video_path, caption, hashtags)

        if result.get("ok"):
            post = PostHistory(
                account_id=account.id,
                platform="TikTok",
                content=caption,
                posted_at=utc_now(),
                source="live_post",
                meta_data=json.dumps({"video_path": video_path, "url": result.get("url")}),
            )
            db.add(post)
            db.commit()
            log_action("live_post", account_id=account.id, status="success", platform="TikTok", details=f"video={video_path}")
        else:
            log_action("live_post", account_id=account.id, status="failed", platform="TikTok", details=result.get("error"))

        return result


def scrape_tiktok_history(account_id: int, max_videos: int = 50) -> Dict:
    with SessionLocal() as db:
        account = db.get(Account, account_id)
        if not account:
            return {"ok": False, "error": "Account not found"}
        if not account.username:
            return {"ok": False, "error": "Account username not set"}

        client = TikTokClient(account)
        videos = client.get_user_videos(account.username, max_videos)

        imported = 0
        for vid in videos:
            existing = db.query(PostHistory).filter(
                PostHistory.account_id == account.id,
                PostHistory.content == vid.get("caption", "")
            ).first()
            if existing:
                continue

            post = PostHistory(
                account_id=account.id,
                platform="TikTok",
                content=vid.get("caption", ""),
                meta_data=json.dumps({"url": vid.get("url"), "source": "scraped"}),
                is_scraped=True,
            )
            db.add(post)
            imported += 1

        db.commit()
        log_action("history_scrape", account_id=account.id, status="success", platform="TikTok", details=f"imported={imported}")
        return {"ok": True, "imported": imported, "total_fetched": len(videos)}
