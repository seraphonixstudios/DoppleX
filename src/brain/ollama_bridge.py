from __future__ import annotations

import json
import requests
from typing import List, Dict, Optional

from utils.logger import get_logger

logger = get_logger("you2.ollama")


class OllamaBridge:
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=3)
            return r.status_code == 200
        except Exception as e:
            logger.debug("Ollama unavailable: %s", e)
            return False

    def list_models(self) -> List[str]:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if r.status_code == 200:
                data = r.json()
                models = data.get("models", [])
                return [m.get("name", m.get("model", "")) for m in models]
        except Exception as e:
            logger.warning("Failed to list Ollama models: %s", e)
        return []

    def chat(self, messages: List[Dict[str, str]], model: str = "qwen3:8b-gpu", temperature: float = 0.7, max_tokens: int = 512) -> Optional[str]:
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
            r = requests.post(url, json=payload, timeout=60)
            if r.status_code == 200:
                data = r.json()
                content = data.get("message", {}).get("content")
                if content:
                    return content
        except Exception as e:
            logger.warning("Ollama chat failed: %s", e)
        return None

    def generate(self, prompt: str, model: str = "qwen3:8b-gpu", temperature: float = 0.7, max_tokens: int = 512) -> Optional[str]:
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
            r = requests.post(url, json=payload, timeout=60)
            if r.status_code == 200:
                data = r.json()
                return data.get("response")
        except Exception as e:
            logger.warning("Ollama generate failed: %s", e)
        return None

    def embeddings(self, text: str, model: str = "qwen3:8b-gpu") -> Optional[List[float]]:
        url = f"{self.base_url}/api/embeddings"
        payload = {
            "model": model,
            "prompt": text,
        }
        try:
            r = requests.post(url, json=payload, timeout=30)
            if r.status_code == 200:
                data = r.json()
                embedding = data.get("embedding")
                if embedding:
                    return embedding
        except Exception as e:
            logger.warning("Ollama embeddings failed: %s", e)
        return None
