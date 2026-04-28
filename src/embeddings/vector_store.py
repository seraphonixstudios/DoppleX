from __future__ import annotations

from typing import List
import json
import math

from models import PostHistory
from db.database import SessionLocal


def _text_to_vector(text: str, dim: int = 512) -> List[float]:
    if not text:
        return [0.0] * dim
    vec = [0.0] * dim
    for word in text.lower().split():
        idx = hash(word) % dim
        vec[idx] += 1.0
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    vec = [v / norm for v in vec]
    return vec


def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5 or 1.0
    norm_b = sum(x * x for x in b) ** 0.5 or 1.0
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def _load_posts_for_account(db, account_id: int) -> List[PostHistory]:
    return db.query(PostHistory).filter(PostHistory.account_id == account_id).order_by(PostHistory.created_at).all()


def top_k_similar_posts(account_id: int, query: str, k: int = 3, dim: int = 512) -> List[PostHistory]:
    with SessionLocal() as db:
        posts = _load_posts_for_account(db, account_id)[:50]
        query_vec = _text_to_vector(query, dim)
        scored = []
        for p in posts:
            vec = _text_to_vector(p.content, dim)
            sim = cosine(query_vec, vec)
            scored.append((sim, p))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored[:max(0, k)]]


def store_embedding_string(account_id: int, embedding_json: str) -> None:
    from models import StyleProfile
    with SessionLocal() as db:
        sp = db.query(StyleProfile).filter(StyleProfile.account_id == account_id).first()
        if not sp:
            sp = StyleProfile(account_id=account_id, profile_json="{}", embedding=embedding_json)
            db.add(sp)
        else:
            sp.embedding = embedding_json
        db.commit()
