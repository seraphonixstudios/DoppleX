from __future__ import annotations

import os


class Settings:
    def __init__(self):
        self.ollama_url = os.environ.get("YOU2_OLLAMA_URL", "http://localhost:11434")
        self.use_dry_run = os.environ.get("YOU2_DRY_RUN", "1") in ("1", "true", "yes")
        self.log_level = os.environ.get("YOU2_LOG_LEVEL", "INFO")
        self.model = os.environ.get("YOU2_OLLA_MODEL", "llama3.2")
        self.db_url = os.environ.get("YOU2_DATABASE_URL", "sqlite:///you2.db")


def load_settings() -> Settings:
    return Settings()
