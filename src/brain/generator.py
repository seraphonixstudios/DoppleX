from __future__ import annotations

import json
import logging
from typing import List

from brain.ollama_bridge import OllamaBridge
from prompts.prompt_builder import build_style_brain_prompt
from embeddings.vector_store import top_k_similar_posts
from models import Account, PostHistory, StyleProfile
from db.database import SessionLocal


class ContentGenerator:
    def __init__(self, ollama_base_url: str = "http://localhost:11434"):
        self.ollama = OllamaBridge(ollama_base_url)
        self.logger = logging.getLogger("you2.contentgen")

    def generate(self, account: Account, last_posts: List[PostHistory]) -> str:
        style_json = account.style_profile.profile_json if account.style_profile else "{}"
        context = ""
        if last_posts:
            try:
                top = top_k_similar_posts(account.id, last_posts[-1].content, k=5)
                if top:
                    context = "\n".join(p.content for p in top)
            except Exception as e:
                self.logger.exception("Memory context retrieval failed: %s", e)
                context = ""
        prompt = build_style_brain_prompt(style_json, last_posts, context=context)
        system_message = {"role": "system", "content": "You are You2.0, a personal AI clone that writes in the user's voice."}
        user_message = {"role": "user", "content": prompt}
        messages = [system_message, user_message]
        content = self.ollama.chat(messages, model="llama3.2", temperature=0.7, max_tokens=512)
        if content:
            self.logger.info("Generated content length=%d for account_id=%s", len(content), getattr(account, 'id', 'unknown'))
            return content.strip()
        self.logger.warning("Ollama content generation failed; falling back to summary of recent posts")
        return self._fallback_style(last_posts)

    def _fallback_style(self, last_posts: List[PostHistory]) -> str:
        text = " ".join(p.content for p in last_posts[-20:]) if last_posts else "Your daily post in your voice."
        if not text:
            text = "Today I want to share something inspiring."
        return f"[{text.split('\n')[0][:120]}] # You2.0 style fallback"

    def generate_and_store(self, account: Account, last_posts: List[PostHistory]) -> str:
        content = self.generate(account, last_posts)
        with SessionLocal() as db:
            post = PostHistory(account_id=account.id, platform=account.platform, content=content, post_id=None, source="brain", brain_model="Ollama llm (Part 3)", generated=True)
            db.add(post)
            db.commit()
        return content
