from __future__ import annotations

import json
from typing import List
from models import PostHistory


def build_style_brain_prompt(style_json: str, last_posts: List[PostHistory], context: str = "") -> str:
    history_text = "\n".join([f"- {p.content}" for p in last_posts[-30:]]) if last_posts else ""
    context_text = f"Similar posts from memory:\n{context}\n" if context else ""

    try:
        style = json.loads(style_json) if style_json else {}
    except Exception:
        style = {}

    tone = style.get("tone", "")
    topics = style.get("topics", [])
    hashtags = style.get("hashtags", [])

    prompt = (
        f"You are writing a social media post. Match the user's voice exactly.\n"
        f"{'Tone: ' + tone + chr(10) if tone else ''}"
        f"{'Topics: ' + ', '.join(topics[:10]) + chr(10) if topics else ''}"
        f"{'Common hashtags: ' + ', '.join(hashtags[:10]) + chr(10) if hashtags else ''}"
        f"{context_text}"
        f"Recent posts for reference:\n{history_text}\n\n"
        f"Write a new post. Be authentic, concise, and engaging."
    )
    return prompt
