from __future__ import annotations

import json
import logging
from typing import List, Optional

from brain.ollama_bridge import OllamaBridge
from prompts.prompt_builder import build_style_brain_prompt
from embeddings.vector_store import top_k_similar_posts
from models import Account, PostHistory, StyleProfile
from db.database import SessionLocal


class ContentGenerator:
    def __init__(self, ollama_base_url: str = "http://localhost:11434"):
        self.ollama = OllamaBridge(ollama_base_url)
        self.logger = logging.getLogger("you2.contentgen")

    def generate(self, account: Account, last_posts: Optional[List[PostHistory]] = None) -> str:
        # Load style profile with real post data from scrapers
        style_json = "{}"
        if account.style_profile and account.style_profile.style_data:
            try:
                style_data = json.loads(account.style_profile.style_data)
                style_json = account.style_profile.style_data
                self.logger.info(f"Using style profile with {len(style_data.get('posts', []))} scraped posts")
            except Exception as e:
                self.logger.warning(f"Failed to parse style profile: {e}")

        # If no posts provided, load from DB (real scraped data)
        if last_posts is None:
            with SessionLocal() as db:
                last_posts = db.query(PostHistory).filter(
                    PostHistory.account_id == account.id
                ).order_by(PostHistory.created_at.desc()).limit(50).all()
                self.logger.info(f"Loaded {len(last_posts)} posts from DB for account {account.username}")

        # Get similar posts from vector store for authentic context
        context = ""
        if last_posts:
            try:
                # Use the most recent post to find similar authentic content
                query = last_posts[0].content if last_posts else ""
                if query:
                    top = top_k_similar_posts(account.id, query, k=5)
                    if top:
                        context = "\n".join(p.content for p in top)
                        self.logger.info(f"Found {len(top)} similar posts for context")
            except Exception as e:
                self.logger.exception("Memory context retrieval failed: %s", e)

        # Build prompt with authentic data
        prompt = build_style_brain_prompt(style_json, last_posts or [], context=context)

        system_message = {
            "role": "system",
            "content": "You are You2.0, a personal AI clone that writes in the user's authentic voice based on their real social media history."
        }
        user_message = {"role": "user", "content": prompt}
        messages = [system_message, user_message]

        content = self.ollama.chat(messages, model="llama3.2", temperature=0.7, max_tokens=512)

        if content:
            self.logger.info("Generated authentic content length=%d for account_id=%s", len(content), getattr(account, 'id', 'unknown'))
            return content.strip()

        self.logger.warning("Ollama content generation failed; falling back to authentic style summary")
        return self._fallback_style(last_posts or [])

    def _fallback_style(self, last_posts: List[PostHistory]) -> str:
        if not last_posts:
            return "Share your thoughts today. #You2.0"

        # Use real post content for fallback
        texts = [p.content for p in last_posts[:20] if p.content]
        if not texts:
            return "Share your thoughts today. #You2.0"

        combined = " ".join(texts)
        # Return a style-mimicking summary
        return f"[{combined[:120]}...] #You2.0 style"

    def generate_and_store(self, account: Account, last_posts: Optional[List[PostHistory]] = None) -> str:
        content = self.generate(account, last_posts)
        with SessionLocal() as db:
            post = PostHistory(
                account_id=account.id,
                platform=account.platform,
                content=content,
                post_id=None,
                source="brain",
                brain_model="llama3.2",
                generated=True
            )
            db.add(post)
            db.commit()
        return content
