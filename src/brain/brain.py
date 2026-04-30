from __future__ import annotations

import json
from typing import List, Optional

from models import PostHistory, MemoryChunk
from db.database import SessionLocal
from brain.ollama_bridge import OllamaBridge
from embeddings.vector_store import VectorStore
from config.settings import load_settings
from utils.logger import get_logger

logger = get_logger("you2.brain")
settings = load_settings()


class BrainEngine:
    def __init__(self, ollama_base_url: str | None = None):
        self.ollama = OllamaBridge(ollama_base_url or settings.ollama_url)
        self.vector_store = VectorStore(ollama_base_url or settings.ollama_url)
        self.model = settings.ollama_model
        self.temperature = settings.temperature
        self.max_tokens = settings.max_tokens
        self.top_k = settings.top_k_memory

    def generate_post(self, account_id: int, topic_hint: str = "", mood: str = "") -> str:
        with SessionLocal() as db:
            from models import Account, StyleProfile
            account = db.get(Account, account_id)
            if not account:
                return "Error: Account not found."

            style_profile = db.query(StyleProfile).filter(StyleProfile.account_id == account_id).first()
            style_json = style_profile.profile_json if style_profile else "{}"

            # Get recent posts for context
            last_posts = db.query(PostHistory).filter(
                PostHistory.account_id == account_id
            ).order_by(PostHistory.created_at.desc()).limit(30).all()

            # RAG: get similar posts from memory
            context_posts = []
            if last_posts:
                query = topic_hint or last_posts[0].content if last_posts else ""
                if query:
                    similar = self.vector_store.search_similar_posts(account_id, query, k=self.top_k)
                    context_posts = [post for post, score in similar if score > 0.5]

            # Get style memory
            style_memory = []
            if style_profile and style_profile.style_summary:
                mems = self.vector_store.search_memory(account_id, style_profile.style_summary, k=3)
                style_memory = [m for m, score in mems if score > 0.3]

            prompt = self._build_prompt(
                style_json=style_json,
                last_posts=last_posts,
                context_posts=context_posts,
                style_memory=style_memory,
                topic_hint=topic_hint,
                mood=mood,
            )

            messages = [
                {"role": "system", "content": "You are You2.0, a personal AI clone that writes social media posts in the user's authentic voice. Match their style, tone, and topics exactly. Do not mention you are an AI."},
                {"role": "user", "content": prompt},
            ]

            content = self.ollama.chat(messages, model=self.model, temperature=self.temperature, max_tokens=self.max_tokens)
            if content:
                return content.strip()

            return self._fallback_style(last_posts)

    def generate_reply(self, account_id: int, original_post: str, platform: str = "X") -> str:
        with SessionLocal() as db:
            from models import Account, StyleProfile
            account = db.get(Account, account_id)
            style_profile = db.query(StyleProfile).filter(StyleProfile.account_id == account_id).first()
            style_json = style_profile.profile_json if style_profile else "{}"

            prompt = (
                f"Write a reply to the following post in the user's authentic voice.\n\n"
                f"Original post: {original_post}\n\n"
                f"User's style: {style_json}\n\n"
                f"Platform: {platform}\n"
                f"Keep it concise and natural."
            )

            messages = [
                {"role": "system", "content": "You are You2.0, a personal AI clone. Write natural replies."},
                {"role": "user", "content": prompt},
            ]

            content = self.ollama.chat(messages, model=self.model, temperature=self.temperature, max_tokens=256)
            return content.strip() if content else "Great post!"

    def _build_prompt(
        self,
        style_json: str,
        last_posts: List[PostHistory],
        context_posts: List[PostHistory],
        style_memory: List[MemoryChunk],
        topic_hint: str,
        mood: str,
    ) -> str:
        try:
            style = json.loads(style_json)
        except Exception:
            style = {}

        history_text = "\n".join([f"- {p.content}" for p in last_posts[:10]]) if last_posts else ""
        context_text = "\n".join([f"- {p.content}" for p in context_posts[:5]]) if context_posts else ""
        memory_text = "\n".join([f"- {m.content}" for m in style_memory[:3]]) if style_memory else ""

        tone = style.get("tone", "")
        topics = style.get("topics", [])
        avg_length = style.get("avg_length", 200)
        hashtags = style.get("hashtags", [])[:10]

        prompt_parts = [
            "Generate a new social media post in the user's voice.",
            f"Tone: {tone}" if tone else "",
            f"Typical topics: {', '.join(topics[:10])}" if topics else "",
            f"Target length: ~{avg_length} characters" if avg_length else "",
            f"Common hashtags: {', '.join(hashtags)}" if hashtags else "",
            f"Topic hint: {topic_hint}" if topic_hint else "",
            f"Mood: {mood}" if mood else "",
        ]

        if memory_text:
            prompt_parts.append(f"\nStyle memory:\n{memory_text}")
        if context_text:
            prompt_parts.append(f"\nSimilar past posts:\n{context_text}")
        if history_text:
            prompt_parts.append(f"\nRecent posts:\n{history_text}")

        prompt_parts.append("\nWrite the post now. Be authentic. Include relevant hashtags if the style uses them.")
        return "\n".join([p for p in prompt_parts if p])

    def _fallback_style(self, last_posts: List[PostHistory]) -> str:
        if not last_posts:
            return "Today I want to share something that matters to me. What do you think?"
        texts = [p.content for p in last_posts[:20] if p.content]
        if not texts:
            return "Today I want to share something that matters to me. What do you think?"
        # Pick a snippet from a recent post and rephrase slightly
        import random
        sample = random.choice(texts)
        return f"Thinking about {sample.split('.')[0][:100]}... What's your take?"
