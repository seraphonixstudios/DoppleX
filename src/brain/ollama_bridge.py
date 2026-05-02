from __future__ import annotations

import aiohttp
from typing import List, Dict, Optional

from utils.logger import get_logger
from utils.error_handler import log_exception

logger = get_logger("you2.ollama")


class OllamaBridge:
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")

    async def is_available(self) -> bool:
        try:
            timeout = aiohttp.ClientTimeout(total=3)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.base_url}/api/tags") as r:
                    return r.status == 200
        except Exception as e:
            log_exception("Ollama health check failed", e, base_url=self.base_url)
            return False

    async def list_models(self) -> List[str]:
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.base_url}/api/tags") as r:
                    if r.status == 200:
                        data = await r.json()
                        models = data.get("models", [])
                        return [m.get("name", m.get("model", "")) for m in models]
        except Exception as e:
            log_exception("Ollama list_models failed", e, base_url=self.base_url)
        return []

    async def chat(self, messages: List[Dict[str, str]], model: str = "qwen3:8b-gpu", temperature: float = 0.7, max_tokens: int = 512) -> Optional[str]:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        try:
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as r:
                    if r.status == 200:
                        data = await r.json()
                        content = data.get("message", {}).get("content")
                        if content:
                            return content
                    else:
                        text = await r.text()
                        logger.warning("Ollama chat returned HTTP %s: %s", r.status, text[:200])
        except Exception as e:
            log_exception("Ollama chat failed", e, model=model, base_url=self.base_url)
        return None

    async def generate(self, prompt: str, model: str = "qwen3:8b-gpu", temperature: float = 0.7, max_tokens: int = 512) -> Optional[str]:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        try:
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as r:
                    if r.status == 200:
                        data = await r.json()
                        return data.get("response")
                    else:
                        text = await r.text()
                        logger.warning("Ollama generate returned HTTP %s: %s", r.status, text[:200])
        except Exception as e:
            log_exception("Ollama generate failed", e, model=model, base_url=self.base_url)
        return None

    async def embeddings(self, text: str, model: str = "qwen3:8b-gpu") -> Optional[List[float]]:
        url = f"{self.base_url}/api/embeddings"
        payload = {
            "model": model,
            "prompt": text,
        }
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as r:
                    if r.status == 200:
                        data = await r.json()
                        embedding = data.get("embedding")
                        if embedding:
                            return embedding
                    else:
                        text = await r.text()
                        logger.warning("Ollama embeddings returned HTTP %s: %s", r.status, text[:200])
        except Exception as e:
            log_exception("Ollama embeddings failed", e, model=model, base_url=self.base_url)
        return None
