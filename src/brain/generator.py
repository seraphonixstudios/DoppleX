from __future__ import annotations

import json
from typing import List, Optional

from models import Account, PostHistory, StyleProfile
from db.database import SessionLocal
from brain.ollama_bridge import OllamaBridge
from brain.brain import BrainEngine
from embeddings.vector_store import VectorStore
from config.settings import load_settings
from utils.logger import get_logger
from utils.audit import log_action
from utils.error_handler import ErrorContext, log_exception

logger = get_logger("you2.generator")
settings = load_settings()


class ContentGenerator:
    def __init__(self, ollama_base_url: str = "http://localhost:11434"):
        self.brain = BrainEngine(ollama_base_url)
        self.vector_store = VectorStore(ollama_base_url)
        self.ollama = OllamaBridge(ollama_base_url)

    def generate(self, account_id: int, topic_hint: str = "", mood: str = "") -> str:
        with ErrorContext("generator.generate", account_id=account_id, topic_hint=topic_hint, mood=mood):
            return self.brain.generate_post(account_id, topic_hint=topic_hint, mood=mood)

    def generate_and_store(self, account_id: int, topic_hint: str = "", mood: str = "") -> str:
        with ErrorContext("generator.generate_and_store", account_id=account_id, topic_hint=topic_hint, mood=mood):
            content = self.generate(account_id, topic_hint=topic_hint, mood=mood)
            with SessionLocal() as db:
                account = db.get(Account, account_id)
                if not account:
                    return content
                post = PostHistory(
                    account_id=account.id,
                    platform=account.platform,
                    content=content,
                    post_id=None,
                    source="brain",
                    brain_model=settings.ollama_model,
                    generated=True,
                )
                db.add(post)
                db.commit()
                db.refresh(post)

                # Generate embedding asynchronously in background
                try:
                    self.vector_store.store_post_embedding(post.id)
                except Exception as e:
                    log_exception("Failed to store embedding", e, post_id=post.id, account_id=account.id)

                log_action("content_generated", account_id=account.id, status="success", details=f"length={len(content)}, model={settings.ollama_model}")
            return content

    def generate_reply(self, account_id: int, original_post: str, platform: str = "X") -> str:
        with ErrorContext("generator.generate_reply", account_id=account_id, platform=platform):
            return self.brain.generate_reply(account_id, original_post, platform)

    def regenerate_variation(self, account_id: int, original_content: str) -> str:
        with ErrorContext("generator.regenerate_variation", account_id=account_id):
            with SessionLocal() as db:
                account = db.get(Account, account_id)
                style_profile = db.query(StyleProfile).filter(StyleProfile.account_id == account_id).first()
                style_json = style_profile.profile_json if style_profile else "{}"

                prompt = (
                    f"Rewrite the following post in the same voice but with different wording. "
                    f"Keep the same meaning and style.\n\n"
                    f"Original: {original_content}\n\n"
                    f"Style: {style_json}\n\n"
                    f"New version:"
                )

                messages = [
                    {"role": "system", "content": "You are You2.0. Rewrite posts while keeping the authentic voice."},
                    {"role": "user", "content": prompt},
                ]

                try:
                    content = self.ollama.chat(messages, model=settings.ollama_model, temperature=settings.temperature + 0.1, max_tokens=settings.max_tokens)
                    return content.strip() if content else original_content
                except Exception as e:
                    log_exception("Regenerate variation failed", e, account_id=account_id)
                    return original_content
