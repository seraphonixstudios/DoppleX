from __future__ annotations

import os
from pathlib import Path
from typing import Optional

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None  # type: ignore

from encryption.crypto import decrypt
import time
import logging


def _ensure_cookies(account) -> Optional[list]:
    if getattr(account, 'cookies_encrypted', None) is None:
        return None
    cookies_json = decrypt(account.cookies_encrypted)
    try:
        return json.loads(cookies_json)
    except Exception:
        return None


def upload_video(account, video_path: str, caption: str, dry_run: bool = False) -> dict:
    # Hardened TikTok upload path with retries and robust selectors
    logger = __import__('logging').getLogger("you2.tiktok")
    if dry_run:
        return {"ok": True, "info": "dry-run"}
    # Hardened TikTok upload path with retries and robust selectors
    logger = logging.getLogger("you2.tiktok")
    if sync_playwright is None:
        return {"ok": False, "error": "Playwright not installed"}

    cookies = _ensure_cookies(account)
    if not cookies:
        return {"ok": False, "error": "No cookies available for TikTok (live/dry-run)."}

    video_path = Path(video_path)
    if not video_path.exists():
        return {"ok": False, "error": f"Video not found: {video_path}"}

    for attempt in range(1, 4):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context()
                page = context.new_page()
                page.goto("https://www.tiktok.com/upload", timeout=60000)
                if cookies:
                    try:
                        context.add_cookies(cookies)
                    except Exception:
                        # If cookies format is not exact, ignore and continue
                        pass
                # Wait and interact with file input and caption reliably
                page.wait_for_selector("input[type='file']", timeout=15000)
                file_input = page.query_selector("input[type='file']")
                if not file_input:
                    raise RuntimeError("TikTok: file input not found")
                file_input.set_input_files(str(video_path))
                cap_input = page.query_selector("textarea[name='caption']")
                if cap_input:
                    cap_input.fill(caption)
                # Try common submit buttons
                submit = page.query_selector("button[type='submit']") or page.query_selector("button:has-text('Post')") or page.query_selector("button:has-text('Publish')")
                if submit:
                    submit.click()
                else:
                    raise RuntimeError("TikTok: no submit button found")
                # Wait a bit for completion
                page.wait_for_navigation(timeout=60000)
                browser.close()
                return {"ok": True, "info": f"TikTok upload attempt {attempt} completed"}
        except Exception as e:
            logger.warning("TikTok upload attempt %d failed: %s", attempt, e)
            try:
                browser.close()
            except Exception:
                pass
            time.sleep(1)
            continue
    return {"ok": False, "error": "TikTok upload failed after retries"}
