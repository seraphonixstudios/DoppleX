from __future__ import annotations

import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import declarative_base

def _get_data_dir() -> Path:
    """Get platform-specific data directory for database and files."""
    if os.name == "nt":  # Windows
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        data_dir = base / "You2SocialBrain"
    elif os.name == "posix":  # macOS/Linux
        if os.uname().sysname == "Darwin":  # macOS
            data_dir = Path.home() / "Library" / "Application Support" / "You2SocialBrain"
        else:  # Linux
            data_dir = Path.home() / ".local" / "share" / "You2SocialBrain"
    else:
        data_dir = Path.cwd() / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir

DATA_DIR = _get_data_dir()
DATABASE_URL = os.environ.get("YOU2_DATABASE_URL", f"sqlite:///{DATA_DIR / 'you2.db'}")

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def init_db():
    Base.metadata.create_all(bind=engine)
