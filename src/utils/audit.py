from __future__ import annotations

from db.database import SessionLocal
from models import AuditLog
from utils.time_utils import utc_now


def log_action(action: str, account_id: int | None = None, status: str | None = None, details: str | None = None, platform: str | None = None) -> None:
    with SessionLocal() as db:
        log = AuditLog(
            timestamp=utc_now(),
            action=action,
            account_id=account_id,
            status=status,
            details=details,
            platform=platform,
        )
        db.add(log)
        db.commit()
