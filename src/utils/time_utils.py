from __future__ import annotations

from datetime import datetime, timezone, timedelta


def utc_now() -> datetime:
    """Return timezone-naive UTC datetime for SQLite compatibility."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
