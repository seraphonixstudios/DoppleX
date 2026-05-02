from __future__ import annotations

import json
import math
import numpy as np
from typing import List, Tuple

from models import PostHistory, MemoryChunk, StyleProfile
from db.database import SessionLocal
from brain.ollama_bridge import OllamaBridge
from config.settings import load_settings

settings = load_settings()


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    if a is None or b is None or a.shape != b.shape:
        return 0.0
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    return float(dot / norm) if norm > 0 else 0.0


class VectorStore:
    def __init__(self, ollama_base_url: str | None = None):
        self.ollama = OllamaBridge(ollama_base_url or settings.ollama_url)
        self.embedding_model = settings.embedding_model
        self.dim = settings.embedding_dim

    async def _get_embedding(self, text: str) -> np.ndarray | None:
        if not text or not text.strip():
            return None
        try:
            vec = await self.ollama.embeddings(text, model=self.embedding_model)
            if vec is not None:
                return np.array(vec, dtype=np.float32)
        except Exception:
            pass
        return self._fallback_embedding(text)

    def _fallback_embedding(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        if not text:
            return vec
        for i, word in enumerate(text.lower().split()):
            idx = hash(word) % self.dim
            vec[idx] += 1.0 + (i * 0.01)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    async def store_post_embedding(self, post_id: int) -> None:
        with SessionLocal() as db:
            post = db.get(PostHistory, post_id)
            if not post or not post.content:
                return
            vec = await self._get_embedding(post.content)
            if vec is not None:
                post.embedding = json.dumps(vec.tolist())
                db.commit()

    async def store_memory_embedding(self, memory_id: int) -> None:
        with SessionLocal() as db:
            chunk = db.get(MemoryChunk, memory_id)
            if not chunk or not chunk.content:
                return
            vec = await self._get_embedding(chunk.content)
            if vec is not None:
                chunk.embedding = json.dumps(vec.tolist())
                db.commit()

    async def store_style_embedding(self, account_id: int) -> None:
        with SessionLocal() as db:
            profile = db.query(StyleProfile).filter(StyleProfile.account_id == account_id).first()
            if not profile or not profile.style_summary:
                return
            vec = await self._get_embedding(profile.style_summary)
            if vec is not None:
                profile.embedding = json.dumps(vec.tolist())
                db.commit()

    def _deserialize(self, embedding_json: str | None) -> np.ndarray | None:
        if not embedding_json:
            return None
        try:
            arr = json.loads(embedding_json)
            return np.array(arr, dtype=np.float32)
        except Exception:
            return None

    async def search_similar_posts(self, account_id: int, query: str, k: int = 5) -> List[Tuple[PostHistory, float]]:
        query_vec = await self._get_embedding(query)
        if query_vec is None:
            return []

        with SessionLocal() as db:
            posts = db.query(PostHistory).filter(
                PostHistory.account_id == account_id,
                PostHistory.embedding.isnot(None)
            ).order_by(PostHistory.created_at.desc()).limit(200).all()

            results = []
            for post in posts:
                vec = self._deserialize(post.embedding)
                if vec is not None:
                    sim = cosine_similarity(query_vec, vec)
                    results.append((post, sim))

            results.sort(key=lambda x: x[1], reverse=True)
            return results[:k]

    async def search_memory(self, account_id: int, query: str, k: int = 5) -> List[Tuple[MemoryChunk, float]]:
        query_vec = await self._get_embedding(query)
        if query_vec is None:
            return []

        with SessionLocal() as db:
            chunks = db.query(MemoryChunk).filter(
                MemoryChunk.account_id == account_id,
                MemoryChunk.embedding.isnot(None)
            ).order_by(MemoryChunk.created_at.desc()).limit(200).all()

            results = []
            for chunk in chunks:
                vec = self._deserialize(chunk.embedding)
                if vec is not None:
                    sim = cosine_similarity(query_vec, vec)
                    results.append((chunk, sim))

            results.sort(key=lambda x: x[1], reverse=True)
            return results[:k]

    async def build_account_memory(self, account_id: int) -> None:
        with SessionLocal() as db:
            posts = db.query(PostHistory).filter(
                PostHistory.account_id == account_id,
                PostHistory.embedding.is_(None)
            ).limit(50).all()
            for post in posts:
                vec = await self._get_embedding(post.content)
                if vec is not None:
                    post.embedding = json.dumps(vec.tolist())
            db.commit()


async def top_k_similar_posts(account_id: int, query: str, k: int = 3) -> List[PostHistory]:
    store = VectorStore()
    results = await store.search_similar_posts(account_id, query, k=k)
    return [post for post, _ in results]


def store_embedding_string(account_id: int, embedding_json: str) -> None:
    with SessionLocal() as db:
        sp = db.query(StyleProfile).filter(StyleProfile.account_id == account_id).first()
        if not sp:
            sp = StyleProfile(account_id=account_id, profile_json="{}", embedding=embedding_json)
            db.add(sp)
        else:
            sp.embedding = embedding_json
        db.commit()
