from __future__ import annotations

import aiohttp
import json
from typing import List, Dict, Optional

from models import Account, PostHistory
from db.database import SessionLocal
from brain.brain import BrainEngine
from x_api.x_client import XClient
from encryption.crypto import decrypt
from utils.logger import get_logger
from utils.audit import log_action
from utils.time_utils import utc_now
from utils.error_handler import ErrorContext, log_exception

logger = get_logger("you2.reply_bot")


class XReplyBot:
    def __init__(self, account: Account):
        self.account = account
        self.client = XClient(account)
        self.brain = BrainEngine()

    async def fetch_mentions(self, max_results: int = 20) -> List[Dict]:
        """Fetch recent mentions for this account."""
        with ErrorContext("fetch_mentions", account_id=self.account.id):
            if not self.account.username:
                logger.error("Account username not set, cannot fetch mentions")
                return []

            # Get user ID first
            user = await self.client.get_user_by_username(self.account.username)
            if not user:
                logger.error("Could not resolve user ID for @%s", self.account.username)
                return []

            user_id = user.get("id")
            if not user_id:
                return []

            url = f"{self.client.BASE_URL}/users/{user_id}/mentions"
            params = {
                "max_results": min(max_results, 100),
                "tweet.fields": "created_at,author_id,conversation_id",
                "expansions": "author_id",
                "user.fields": "username",
            }

            # If we have a last seen mention ID, fetch only newer ones
            if self.account.last_mention_id:
                params["since_id"] = self.account.last_mention_id

            try:
                timeout = aiohttp.ClientTimeout(total=15)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, params=params, headers=self.client._headers()) as resp:
                        if resp.status != 200:
                            text_body = await resp.text()
                            logger.error("Mentions fetch failed: %s", text_body)
                            return []

                        data = await resp.json()
                        mentions = data.get("data", [])
                        users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}

                        # Enrich with author username
                        for m in mentions:
                            author_id = m.get("author_id")
                            if author_id and author_id in users:
                                m["author_username"] = users[author_id].get("username", "unknown")

                        return mentions
            except Exception as e:
                log_exception("Failed to fetch mentions", e, account_id=self.account.id)
                return []

    async def generate_reply(self, mention_text: str, author_username: str) -> str:
        """Generate a reply in the user's voice."""
        with ErrorContext("generate_reply", account_id=self.account.id):
            prompt = (
                f"@{author_username} mentioned you: '{mention_text}'\n\n"
                f"Write a friendly, natural reply in your authentic voice. "
                f"Keep it concise (under 280 chars if possible). "
                f"Don't be overly formal. Match your usual style."
            )
            try:
                return await self.brain.generate_reply(self.account.id, prompt, platform="X")
            except Exception as e:
                log_exception("Reply generation failed", e, account_id=self.account.id)
                return "Thanks for the mention!"

    async def reply_to_mention(self, mention: Dict) -> Dict:
        """Generate and post a reply to a single mention."""
        with ErrorContext("reply_to_mention", account_id=self.account.id):
            tweet_id = mention.get("id")
            mention_text = mention.get("text", "")
            author = mention.get("author_username", "user")

            if not tweet_id:
                return {"ok": False, "error": "Missing tweet ID"}

            # Check if we already replied
            with SessionLocal() as db:
                existing = db.query(PostHistory).filter(
                    PostHistory.account_id == self.account.id,
                    PostHistory.reply_to_id == tweet_id,
                ).first()
                if existing:
                    return {"ok": False, "error": "Already replied to this mention"}

            # Generate reply
            reply_text = await self.generate_reply(mention_text, author)
            if not reply_text:
                return {"ok": False, "error": "Reply generation failed"}

            # Post reply
            result = await self.client.post_tweet(reply_text, reply_to=tweet_id)
            if result.get("ok"):
                # Store in history
                with SessionLocal() as db:
                    post = PostHistory(
                        account_id=self.account.id,
                        platform="X",
                        content=reply_text,
                        post_id=result.get("tweet_id"),
                        posted_at=utc_now(),
                        source="reply_bot",
                        reply_to_id=tweet_id,
                        reply_to_username=author,
                    )
                    db.add(post)

                    # Update last mention ID
                    acc = db.get(Account, self.account.id)
                    if acc:
                        current_last = acc.last_mention_id or "0"
                        if tweet_id > current_last:
                            acc.last_mention_id = tweet_id
                    db.commit()

                log_action("reply_bot", account_id=self.account.id, status="success", platform="X", details=f"replied_to={author}, tweet_id={tweet_id}")
                logger.info("Replied to @%s: %s", author, reply_text[:80])
            else:
                log_action("reply_bot", account_id=self.account.id, status="failed", platform="X", details=result.get("error"))
                logger.error("Reply post failed: %s", result.get("error"))

            return result

    async def run_once(self) -> Dict:
        """Check mentions and reply to all new ones."""
        with ErrorContext("reply_bot_run_once", account_id=self.account.id):
            if not self.account.reply_bot_enabled:
                return {"ok": False, "error": "Reply bot disabled"}

            mentions = await self.fetch_mentions()
            if not mentions:
                return {"ok": True, "replied": 0, "info": "No new mentions"}

            replied = 0
            for mention in mentions:
                # Skip self-mentions
                author = mention.get("author_username", "").lower()
                if author == (self.account.username or "").lower():
                    continue

                res = await self.reply_to_mention(mention)
                if res.get("ok"):
                    replied += 1

                # Update last mention ID regardless of reply success
                with SessionLocal() as db:
                    acc = db.get(Account, self.account.id)
                    if acc:
                        tweet_id = mention.get("id")
                        current_last = acc.last_mention_id or "0"
                        if tweet_id > current_last:
                            acc.last_mention_id = tweet_id
                    db.commit()

            return {"ok": True, "replied": replied, "mentions_checked": len(mentions)}
