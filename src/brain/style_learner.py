from __future__ import annotations

import json
import re
from typing import List, Dict, Optional
from collections import Counter

from models import Account, PostHistory, StyleProfile, MemoryChunk
from db.database import SessionLocal
from brain.ollama_bridge import OllamaBridge
from config.settings import load_settings
from utils.logger import get_logger

logger = get_logger("you2.style")
settings = load_settings()


class StyleLearner:
    def __init__(self, ollama_base_url: str | None = None):
        self.ollama = OllamaBridge(ollama_base_url or settings.ollama_url)
        self.model = settings.ollama_model

    def analyze_account(self, account_id: int, force: bool = False) -> StyleProfile:
        with SessionLocal() as db:
            account = db.get(Account, account_id)
            if not account:
                raise ValueError(f"Account {account_id} not found")

            profile = db.query(StyleProfile).filter(StyleProfile.account_id == account_id).first()
            if not profile:
                profile = StyleProfile(account_id=account_id, profile_json="{}")
                db.add(profile)
                db.commit()
                db.refresh(profile)

            posts = db.query(PostHistory).filter(
                PostHistory.account_id == account_id,
                PostHistory.content.isnot(None)
            ).order_by(PostHistory.created_at.desc()).limit(100).all()

            if not posts:
                logger.warning("No posts found for account %d", account_id)
                return profile

            texts = [p.content for p in posts if p.content]
            style_data = self._extract_style(texts)

            profile.profile_json = json.dumps(style_data, ensure_ascii=False)
            profile.style_summary = style_data.get("summary", "")
            profile.tone = style_data.get("tone", "")
            profile.topics = json.dumps(style_data.get("topics", []), ensure_ascii=False)
            profile.common_hashtags = json.dumps(style_data.get("hashtags", []), ensure_ascii=False)
            profile.avg_post_length = style_data.get("avg_length", 0)
            from utils.time_utils import utc_now
            profile.updated_at = utc_now()
            db.commit()
            db.refresh(profile)

            # Store style as memory
            memory = MemoryChunk(
                account_id=account_id,
                chunk_type="style",
                content=profile.style_summary or json.dumps(style_data)
            )
            db.add(memory)
            db.commit()

            # Eagerly load attributes to avoid detached instance errors
            _ = profile.tone
            _ = profile.avg_post_length
            _ = profile.style_summary
            _ = profile.topics
            _ = profile.common_hashtags
            _ = profile.profile_json

            logger.info("Style analysis complete for account %d", account_id)
            return profile

    def _extract_style(self, texts: List[str]) -> Dict:
        if not texts:
            return {}

        all_text = "\n".join(texts)
        avg_length = int(sum(len(t) for t in texts) / len(texts))

        # Extract hashtags
        hashtags = re.findall(r'#\w+', all_text)
        top_hashtags = [tag for tag, _ in Counter(hashtags).most_common(20)]

        # Extract mentions
        mentions = re.findall(r'@\w+', all_text)
        top_mentions = [m for m, _ in Counter(mentions).most_common(10)]

        # Common words (simple)
        words = re.findall(r'\b[a-z]{4,}\b', all_text.lower())
        stopwords = {'this', 'that', 'with', 'from', 'have', 'been', 'were', 'they', 'will', 'would', 'could', 'should', 'about', 'there', 'their', 'what', 'when', 'where', 'which', 'while', 'than', 'then', 'them', 'these', 'those', 'because', 'before', 'after', 'above', 'below', 'between', 'under', 'over', 'again', 'further', 'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all', 'each', 'few', 'more', 'most', 'other', 'some', 'such', 'only', 'own', 'same', 'than', 'too', 'very', 'just', 'also', 'back', 'still', 'well', 'even', 'like', 'know', 'make', 'take', 'come', 'want', 'look', 'use', 'find', 'give', 'tell', 'ask', 'work', 'seem', 'feel', 'try', 'leave', 'call', 'good', 'new', 'first', 'last', 'long', 'great', 'little', 'own', 'other', 'old', 'right', 'big', 'high', 'different', 'small', 'large', 'next', 'early', 'young', 'important', 'few', 'public', 'bad', 'same', 'able'}
        filtered = [w for w in words if w not in stopwords]
        top_words = [w for w, _ in Counter(filtered).most_common(30)]

        # Use Ollama for deeper analysis if available
        tone = ""
        summary = ""
        topics = []

        if self.ollama.is_available() and len(texts) >= 3:
            sample = "\n---\n".join(texts[:20])
            analysis_prompt = (
                f"Analyze the following social media posts and describe the writing style. "
                f"Return ONLY a JSON object with keys: tone (single adjective), topics (list of 5-10 strings), "
                f"summary (2-3 sentence description of the writing style).\n\nPosts:\n{sample}\n\nJSON:"
            )
            try:
                response = self.ollama.generate(analysis_prompt, model=self.model, temperature=0.3, max_tokens=512)
                if response:
                    parsed = self._extract_json(response)
                    tone = parsed.get("tone", "")
                    topics = parsed.get("topics", [])
                    summary = parsed.get("summary", "")
            except Exception as e:
                logger.warning("Ollama style analysis failed: %s", e)

        if not tone:
            tone = self._heuristic_tone(texts)
        if not summary:
            summary = f"Average post length: {avg_length} chars. Uses hashtags: {', '.join(top_hashtags[:5])}."
        if not topics:
            topics = top_words[:10]

        return {
            "tone": tone,
            "topics": topics,
            "summary": summary,
            "hashtags": top_hashtags,
            "mentions": top_mentions,
            "top_words": top_words,
            "avg_length": avg_length,
            "post_count": len(texts),
        }

    def _heuristic_tone(self, texts: List[str]) -> str:
        all_text = " ".join(texts).lower()
        scores = {
            "casual": all_text.count("!") + all_text.count("lol") + all_text.count("haha"),
            "formal": all_text.count(".") / max(len(texts), 1),
            "enthusiastic": all_text.count("!") + all_text.count("love") + all_text.count("amazing"),
            "professional": all_text.count("team") + all_text.count("business") + all_text.count("work"),
        }
        return max(scores, key=scores.get) if scores else "neutral"

    def _extract_json(self, text: str) -> Dict:
        try:
            # Try to find JSON in response
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group())
            return json.loads(text)
        except Exception:
            return {}
