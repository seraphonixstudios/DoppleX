from __future__ import annotations

from datetime import datetime

from db.database import SessionLocal
from models import AuditLog


def log_action(action: str, account_id: int | None = None, status: str | None = None, details: str | None = None) -> None:
    with SessionLocal() as db:
        log = AuditLog(
            timestamp=datetime.utcnow(),
            action=action,
            account_id=account_id,
            status=status,
            details=details,
        )
        db.add(log)
        db.commit()
