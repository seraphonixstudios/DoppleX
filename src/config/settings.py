from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional


class Settings:
    def __init__(self):
        self.ollama_url = os.environ.get("YOU2_OLLAMA_URL", "http://localhost:11434")
        self.ollama_model = os.environ.get("YOU2_OLLAMA_MODEL", "")
        self.embedding_model = os.environ.get("YOU2_EMBEDDING_MODEL", "")
        self.use_dry_run = os.environ.get("YOU2_DRY_RUN", "0").lower() in ("1", "true", "yes")
        self.log_level = os.environ.get("YOU2_LOG_LEVEL", "INFO")
        self.db_url = os.environ.get("YOU2_DATABASE_URL", "sqlite:///you2.db")
        self.data_dir = self._get_data_dir()
        
        # X API settings
        self.x_client_id = os.environ.get("YOU2_X_CLIENT_ID", "")
        self.x_client_secret = os.environ.get("YOU2_X_CLIENT_SECRET", "")
        self.x_bearer_token = os.environ.get("YOU2_X_BEARER_TOKEN", "")
        self.x_api_key = os.environ.get("YOU2_X_API_KEY", "")
        self.x_api_secret = os.environ.get("YOU2_X_API_SECRET", "")
        
        # TikTok settings
        self.tiktok_client_id = os.environ.get("YOU2_TIKTOK_CLIENT_ID", "")
        self.tiktok_client_secret = os.environ.get("YOU2_TIKTOK_CLIENT_SECRET", "")
        
        # Scheduler
        self.scheduler_timezone = os.environ.get("YOU2_TIMEZONE", "UTC")
        self.max_retries = int(os.environ.get("YOU2_MAX_RETRIES", "3"))
        
        # Image generation
        self.sd_webui_url = os.environ.get("YOU2_SD_URL", "http://localhost:7860")
        
        # Content generation
        self.temperature = float(os.environ.get("YOU2_TEMPERATURE", "0.7"))
        self.max_tokens = int(os.environ.get("YOU2_MAX_TOKENS", "512"))
        self.top_k_memory = int(os.environ.get("YOU2_TOP_K_MEMORY", "5"))
        self.embedding_dim = int(os.environ.get("YOU2_EMBEDDING_DIM", "768"))

    def _get_data_dir(self) -> Path:
        if os.name == "nt":
            base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
            data_dir = base / "You2SocialBrain"
        elif os.name == "posix":
            if hasattr(os, 'uname') and os.uname().sysname == "Darwin":
                data_dir = Path.home() / "Library" / "Application Support" / "You2SocialBrain"
            else:
                data_dir = Path.home() / ".local" / "share" / "You2SocialBrain"
        else:
            data_dir = Path.cwd() / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    @property
    def _settings_path(self) -> Path:
        return self.data_dir / "settings.json"

    def load_from_disk(self) -> None:
        """Override defaults with persisted settings from disk."""
        path = self._settings_path
        if not path.exists():
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key, value in data.items():
                if hasattr(self, key) and key != "data_dir":
                    # Type coercion for numeric fields
                    if key in ("max_retries", "max_tokens", "top_k_memory", "embedding_dim"):
                        value = int(value)
                    elif key in ("temperature",):
                        value = float(value)
                    elif key == "use_dry_run":
                        value = bool(value)
                    setattr(self, key, value)
        except Exception:
            pass

    def save_to_disk(self) -> None:
        """Persist current settings to disk."""
        data = {
            "ollama_url": self.ollama_url,
            "ollama_model": self.ollama_model,
            "embedding_model": self.embedding_model,
            "use_dry_run": self.use_dry_run,
            "log_level": self.log_level,
            "sd_webui_url": self.sd_webui_url,
            "scheduler_timezone": self.scheduler_timezone,
            "max_retries": self.max_retries,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_k_memory": self.top_k_memory,
            "embedding_dim": self.embedding_dim,
        }
        try:
            with open(self._settings_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def get_db_url(self) -> str:
        if self.db_url.startswith("sqlite:///") and not self.db_url.startswith("sqlite:////"):
            return f"sqlite:///{self.data_dir / 'you2.db'}"
        return self.db_url


def detect_models(ollama_url: str = "http://localhost:11434") -> tuple[str, str]:
    """Auto-detect available Ollama models and return (chat_model, embedding_model)."""
    import requests
    from utils.logger import get_logger
    logger = get_logger("you2.settings")
    
    try:
        r = requests.get(f"{ollama_url.rstrip('/')}/api/tags", timeout=3)
        if r.status_code != 200:
            logger.warning("Could not reach Ollama at %s", ollama_url)
            return "qwen3:8b-gpu", "qwen3:8b-gpu"
        
        data = r.json()
        models = [m.get("name", m.get("model", "")) for m in data.get("models", [])]
        logger.info("Detected Ollama models: %s", models)
        
        if not models:
            logger.warning("No Ollama models found, using defaults")
            return "qwen3:8b-gpu", "qwen3:8b-gpu"
        
        chat_candidates = [m for m in models if "llava" not in m.lower()]
        if not chat_candidates:
            chat_candidates = models
        
        chat_model = None
        for candidate in chat_candidates:
            if "qwen3" in candidate.lower():
                chat_model = candidate
                break
        if not chat_model:
            for candidate in chat_candidates:
                if "dolphin" in candidate.lower():
                    chat_model = candidate
                    break
        if not chat_model:
            chat_model = chat_candidates[0]
        
        embed_model = None
        for candidate in models:
            if "qwen3" in candidate.lower():
                embed_model = candidate
                break
        if not embed_model:
            for candidate in models:
                if "dolphin" in candidate.lower():
                    embed_model = candidate
                    break
        if not embed_model:
            embed_model = models[0]
        
        logger.info("Auto-selected chat model: %s, embedding model: %s", chat_model, embed_model)
        return chat_model, embed_model
        
    except Exception as e:
        logger.warning("Model detection failed: %s", e)
        return "qwen3:8b-gpu", "qwen3:8b-gpu"


_SETTINGS_CACHE: Settings | None = None

def load_settings() -> Settings:
    global _SETTINGS_CACHE
    if _SETTINGS_CACHE is not None:
        return _SETTINGS_CACHE

    settings = Settings()
    settings.load_from_disk()

    # Auto-detect models if not explicitly set by environment or disk
    if not settings.ollama_model or not settings.embedding_model:
        chat, embed = detect_models(settings.ollama_url)
        if not settings.ollama_model:
            settings.ollama_model = chat
        if not settings.embedding_model:
            settings.embedding_model = embed

    _SETTINGS_CACHE = settings
    return settings
