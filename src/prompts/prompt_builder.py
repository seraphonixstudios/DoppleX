from __future__ annotations

import json
from typing import List
from models import PostHistory


def build_style_brain_prompt(style_json: str, last_posts: List[PostHistory], context: str = "") -> str:
    # Build a compact system prompt incorporating style and history
    history_text = "\n".join([p.content for p in last_posts[-30:]]) if last_posts else ""
    context_text = f"Context:\n{context}\n" if context else ""
    prompt = (
        "Using the following style profile and recent posts, generate a new post in the user's voice.\n"
        f"Style profile: {style_json}\n"
        f"{context_text}"
        f"Recent history:\n{history_text}\n"
        "Include relevant hashtags and keep the post concise."
    )
    return prompt
