from __future__ import annotations

import aiohttp
import json
from typing import List, Dict, Optional
from datetime import datetime

from encryption.crypto import decrypt
from models import Account, PostHistory
from db.database import SessionLocal
from utils.logger import get_logger
from utils.audit import log_action
from utils.time_utils import utc_now
from utils.error_handler import ErrorContext, log_exception
from config.settings import load_settings

logger = get_logger("you2.x_client")
settings = load_settings()


class XClient:
    BASE_URL = "https://api.twitter.com/2"
    UPLOAD_URL = "https://upload.twitter.com/1.1"

    def __init__(self, account: Account):
        self.account = account
        self.bearer_token = self._decrypt_field(account.token_encrypted)
        self.api_key = self._decrypt_field(account.api_key_encrypted)
        self.api_secret = self._decrypt_field(account.api_secret_encrypted)

    def _decrypt_field(self, field: str | None) -> str | None:
        if not field:
            return None
        try:
            return decrypt(field)
        except Exception as e:
            logger.error("Failed to decrypt field: %s", e)
            return None

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        return headers

    async def post_tweet(self, text: str, reply_to: str | None = None, media_ids: List[str] | None = None) -> Dict:
        if not self.bearer_token:
            return {"ok": False, "error": "No bearer token available"}

        url = f"{self.BASE_URL}/tweets"
        payload = {"text": text}
        if reply_to:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to}
        if media_ids:
            payload["media"] = {"media_ids": media_ids}

        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload, headers=self._headers()) as resp:
                    if resp.status in (200, 201):
                        data = await resp.json()
                        tweet_id = data.get("data", {}).get("id")
                        logger.info("Tweet posted successfully: %s", tweet_id)
                        return {"ok": True, "data": data, "tweet_id": tweet_id}
                    text_body = await resp.text()
                    logger.error("Tweet failed: %s - %s", resp.status, text_body)
                    return {"ok": False, "error": f"HTTP {resp.status}: {text_body}"}
        except Exception as e:
            log_exception("X API post_tweet failed", e, account_id=self.account.id, platform="X")
            return {"ok": False, "error": str(e), "error_type": type(e).__name__}

    async def get_user_tweets(self, user_id: str, max_results: int = 100) -> List[Dict]:
        if not self.bearer_token:
            logger.error("No bearer token for get_user_tweets")
            return []

        url = f"{self.BASE_URL}/users/{user_id}/tweets"
        params = {
            "max_results": min(max_results, 100),
            "tweet.fields": "created_at,public_metrics,entities,source",
            "exclude": "replies,retweets",
        }

        tweets = []
        pagination_token = None

        while len(tweets) < max_results:
            if pagination_token:
                params["pagination_token"] = pagination_token

            try:
                timeout = aiohttp.ClientTimeout(total=15)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, params=params, headers=self._headers()) as resp:
                        if resp.status != 200:
                            text_body = await resp.text()
                            logger.error("Failed to fetch tweets: %s", text_body)
                            break
                        data = await resp.json()
                        batch = data.get("data", [])
                        tweets.extend(batch)
                        pagination_token = data.get("meta", {}).get("next_token")
                        if not pagination_token or not batch:
                            break
            except Exception as e:
                log_exception("X API get_user_tweets failed", e, account_id=self.account.id, user_id=user_id)
                break

        return tweets[:max_results]

    async def get_user_by_username(self, username: str) -> Optional[Dict]:
        if not self.bearer_token:
            return None
        url = f"{self.BASE_URL}/users/by/username/{username}"
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=self._headers()) as resp:
                    if resp.status == 200:
                        return (await resp.json()).get("data")
        except Exception as e:
            log_exception("X API get_user_by_username failed", e, username=username)
        return None

    async def upload_media(self, media_path: str) -> Optional[str]:
        if not self.api_key or not self.api_secret:
            logger.error("Media upload requires API key/secret (OAuth 1.0a)")
            return None

        access_token = self._decrypt_field(self.account.access_token_encrypted)
        access_token_secret = self._decrypt_field(self.account.access_token_secret_encrypted)
        if not access_token or not access_token_secret:
            logger.error("Media upload requires OAuth 1.0a access token/secret")
            return None

        try:
            from requests_oauthlib import OAuth1
            import requests
            auth = OAuth1(self.api_key, self.api_secret, access_token, access_token_secret)
            url = f"{self.UPLOAD_URL}/media/upload.json"

            with open(media_path, "rb") as f:
                files = {"media": f}
                resp = requests.post(url, auth=auth, files=files, timeout=30)

            if resp.status_code == 200:
                data = resp.json()
                media_id = data.get("media_id_string")
                logger.info("Media uploaded: %s", media_id)
                return media_id
            else:
                logger.error("Media upload failed: %s - %s", resp.status_code, resp.text)
                return None
        except Exception as e:
            log_exception("X API upload_media failed", e, account_id=self.account.id, media_path=media_path)
            return None


async def post_tweet(account_id: int, content: str, reply_to: str | None = None) -> Dict:
    with ErrorContext("post_tweet", account_id=account_id, content_len=len(content)):
        with SessionLocal() as db:
            account = db.get(Account, account_id)
            if not account:
                return {"ok": False, "error": "Account not found"}
            client = XClient(account)
            result = await client.post_tweet(content, reply_to=reply_to)
            if result.get("ok"):
                post = PostHistory(
                    account_id=account.id,
                    platform="X",
                    content=content,
                    post_id=result.get("tweet_id"),
                    posted_at=utc_now(),
                    source="live_post",
                    meta_data=json.dumps({"reply_to": reply_to}),
                )
                db.add(post)
                db.commit()
                log_action("live_post", account_id=account.id, status="success", platform="X", details=f"tweet_id={result.get('tweet_id')}")
            else:
                log_action("live_post", account_id=account.id, status="failed", platform="X", details=result.get("error"))
            return result


async def fetch_user_history(account_id: int, max_results: int = 100) -> Dict:
    with ErrorContext("fetch_user_history", account_id=account_id, max_results=max_results):
        with SessionLocal() as db:
            account = db.get(Account, account_id)
            if not account:
                return {"ok": False, "error": "Account not found"}

            client = XClient(account)
            username = account.username
            if not username:
                return {"ok": False, "error": "Account username not set"}

            user = await client.get_user_by_username(username)
            if not user:
                return {"ok": False, "error": f"Could not find user @{username}"}

            user_id = user.get("id")
            tweets = await client.get_user_tweets(user_id, max_results=max_results)

            imported = 0
            for tweet in tweets:
                existing = db.query(PostHistory).filter(
                    PostHistory.account_id == account.id,
                    PostHistory.post_id == tweet.get("id")
                ).first()
                if existing:
                    continue

                metrics = tweet.get("public_metrics", {})
                post = PostHistory(
                    account_id=account.id,
                    platform="X",
                    post_id=tweet.get("id"),
                    content=tweet.get("text", ""),
                    posted_at=tweet.get("created_at"),
                    engagement=json.dumps(metrics),
                    meta_data=json.dumps({"source": "api_fetch", "entities": tweet.get("entities", {})}),
                    is_scraped=True,
                )
                db.add(post)
                imported += 1

            db.commit()
            log_action("history_scrape", account_id=account.id, status="success", platform="X", details=f"imported={imported}")
            return {"ok": True, "imported": imported, "total_fetched": len(tweets)}
