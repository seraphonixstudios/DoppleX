from __future__ import annotations

import json
import requests
from typing import List, Dict, Optional


class OllamaBridge:
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/v1/models", timeout=2)
            return r.status_code == 200
        except Exception:
            return False

    def chat(self, messages: List[Dict[str, str]], model: str = "llama3.2", temperature: float = 0.7, max_tokens: int = 512) -> Optional[str]:
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        try:
            r = requests.post(url, json=payload, timeout=20)
            if r.status_code == 200:
                data = r.json()
                # Typical OpenAI-like response structure
                if data and data.get("choices"):
                    return data["choices"][0]["message"]["content"]
        except Exception:
            pass
        return None
