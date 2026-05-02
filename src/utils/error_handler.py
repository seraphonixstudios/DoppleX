from __future__ import annotations

import functools
import logging
import traceback
import json
from typing import Callable, Dict, Optional, Any


def _lazy_import_db():
    """Lazy import to avoid circular dependencies."""
    try:
        from db.database import SessionLocal
        from models import AuditLog
        from utils.time_utils import utc_now
        return SessionLocal, AuditLog, utc_now
    except Exception:
        return None, None, None


def log_exception(message: str, exc: Exception, **context) -> None:
    """Log an exception with structured context."""
    logger = logging.getLogger("you2.error")
    ctx_str = " | ".join(f"{k}={v}" for k, v in context.items()) if context else ""
    logger.error(f"{message} | Exception: {type(exc).__name__}: {exc}{' | ' + ctx_str if ctx_str else ''}")
    logger.debug("Traceback:\n%s", traceback.format_exc())


def safe_call(description: str, func, *args, **kwargs):
    """Wrap a function call with error handling and recovery hints."""
    try:
        value = func(*args, **kwargs)
        return {"ok": True, "value": value}
    except Exception as e:
        log_exception(description, e)
        hint = _get_recovery_hint(e)
        return {
            "ok": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "trace": traceback.format_exc(),
            "recovery_hint": hint,
        }


def _get_recovery_hint(exc: Exception) -> str:
    """Return a user-friendly recovery hint based on exception type."""
    name = type(exc).__name__
    msg = str(exc).lower()
    
    hints = {
        "ConnectionError": "Check your internet connection and try again.",
        "TimeoutError": "The server took too long to respond. Try again later.",
        "ModuleNotFoundError": f"Missing dependency: {exc}. Run: pip install -r requirements.txt",
        "FileNotFoundError": f"File not found: {exc}. Check the path and try again.",
        "PermissionError": "Permission denied. Try running as administrator or check file permissions.",
        "ValueError": "Invalid input provided. Check your arguments and try again.",
        "KeyError": "Missing configuration key. Check your settings and environment variables.",
        "SQLAlchemyError": "Database error. Try restarting the app or check database permissions.",
        "RequestException": "Network request failed. Check your connection and API credentials.",
        "OperationalError": "Database is locked or unavailable. Restart the app.",
        "IntegrityError": "Database constraint violation. Check for duplicates or invalid data.",
    }
    
    # Check for specific patterns in message
    if "ollama" in msg or "11434" in msg:
        return "Ollama is not running. Start it with: ollama serve"
    if "playwright" in msg:
        return "Playwright not installed. Run: playwright install"
    if "oauth" in msg or "token" in msg or "credential" in msg:
        return "Authentication failed. Check your API tokens and credentials."
    if "rate limit" in msg or "429" in msg:
        return "Rate limited by API. Wait a few minutes and try again."
    if "media" in msg or "upload" in msg:
        return "Media upload failed. Check file exists and is under size limits."
    if "no such table" in msg:
        return "Database schema is missing. Run the app once to initialize tables."
    if "foreign key" in msg:
        return "Referenced record does not exist. Check account IDs and references."
    
    return hints.get(name, "An unexpected error occurred. Check the logs for details.")


class ErrorContext:
    """Structured error context for rich logging and reporting."""
    
    def __init__(self, operation: str, account_id: Optional[int] = None, **context):
        self.operation = operation
        self.account_id = account_id
        self.context = context
        self.errors: list[Dict[str, Any]] = []
        self.logger = logging.getLogger("you2.error")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val:
            self.record_error(exc_val, traceback.format_exc())
            return False  # Don't suppress
        return True
    
    def record_error(self, exc: Exception, trace: Optional[str] = None) -> Dict:
        """Record an error with full context."""
        SessionLocal, AuditLog, utc_now = _lazy_import_db()
        
        error_record = {
            "timestamp": datetime.now().isoformat() if utc_now is None else utc_now().isoformat(),
            "operation": self.operation,
            "account_id": self.account_id,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "context": self.context,
            "traceback": trace or traceback.format_exc(),
            "recovery_hint": _get_recovery_hint(exc),
        }
        self.errors.append(error_record)
        
        # Log structured error
        ctx = json.dumps(self.context, default=str) if self.context else "{}"
        self.logger.error(
            f"OPERATION_FAILED | op={self.operation} | account={self.account_id} | "
            f"type={type(exc).__name__} | msg={str(exc)} | context={ctx}"
        )
        self.logger.debug("Traceback:\n%s", error_record["traceback"])
        
        # Write to audit log (best effort)
        if SessionLocal and AuditLog and utc_now:
            try:
                with SessionLocal() as db:
                    log = AuditLog(
                        timestamp=utc_now(),
                        action=f"error:{self.operation}",
                        account_id=self.account_id,
                        status="error",
                        details=json.dumps(error_record, default=str)[:2000],
                    )
                    db.add(log)
                    db.commit()
            except Exception:
                pass
        
        return error_record
    
    def wrap(self, func: Callable) -> Callable:
        """Decorator to wrap a function with this error context."""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                self.record_error(e)
                raise
        return wrapper


def with_error_context(operation: str, account_id_key: Optional[str] = None):
    """Decorator factory for automatic error context wrapping."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            aid = kwargs.get(account_id_key) if account_id_key else None
            if aid is None and args:
                # Try to infer account_id from first positional arg if it's an int
                if isinstance(args[0], int):
                    aid = args[0]
            
            with ErrorContext(operation, account_id=aid):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    hint = _get_recovery_hint(e)
                    # Re-raise with enhanced message
                    raise type(e)(f"[{operation}] {str(e)} (Hint: {hint})") from e
        return wrapper
    return decorator


def notify_error(title: str, message: str, tray_manager=None):
    """Notify user of an error via tray and logs."""
    logger = logging.getLogger("you2.error")
    logger.error(f"USER_NOTIFICATION | {title}: {message}")
    
    if tray_manager and hasattr(tray_manager, 'notify'):
        try:
            tray_manager.notify(title, message)
        except Exception:
            pass


from datetime import datetime  # noqa: E402 - import at end to avoid circular issues if any
