from __future__ import annotations

from typing import List
from db.database import SessionLocal
from models import Account, PostHistory, StyleProfile
from encryption.crypto import decrypt
from brain.ollama_bridge import OllamaBridge
from prompts.prompt_builder import build_style_brain_prompt
from embeddings.vector_store import top_k_similar_posts


class BrainEngine:
    def __init__(self, ollama_base_url: str | None = None):
        self.ollama = OllamaBridge(ollama_base_url or "http://localhost:11434")

    def generate_post(self, account: Account, last_posts: List[PostHistory]) -> str:
        # Build a simplified style prompt
        style_json = (account.style_profile.profile_json if account.style_profile else "{}")
        # Build context from memory (top-k similar posts) if available
        context = ""
        if last_posts:
            try:
                top = top_k_similar_posts(account.id, last_posts[-1].content, k=3)
                if top:
                    context = "\n".join([p.content for p in top])
            except Exception:
                context = ""
        prompt = build_style_brain_prompt(style_json, last_posts, context=context)
        messages = [
            {"role": "system", "content": "You are You2.0, a personal AI clone that writes in the user's voice."},
            {"role": "user", "content": prompt},
        ]
        content = self.ollama.chat(messages, model="llama3.2", temperature=0.7, max_tokens=512)
        if content:
            return content.strip()
        # Fallback simple heuristic if Ollama is not available
        return self._fallback_style(last_posts)

    def _fallback_style(self, last_posts: List[PostHistory]) -> str:
        # Very simple heuristic: reuse vocabulary from last posts
        text = " ".join((p.content for p in last_posts[-20:])) if last_posts else "Your daily post in your voice."
        if not text:
            text = "Today I want to share something inspiring."
        return f"[{text.split('\n')[0][:120]}] # You2.0 style fallback"
