from __future__ import annotations

import logging
import traceback


def log_exception(message: str, exc: Exception) -> None:
    logger = logging.getLogger("you2.error")
    logger.error(message + f" | Exception: {type(exc).__name__}: {exc}")
    logger.debug("Traceback:\n%s", traceback.format_exc())


def safe_call(description: str, func, *args, **kwargs):
    try:
        value = func(*args, **kwargs)
        return {"ok": True, "value": value}
    except Exception as e:
        log_exception(description, e)
        return {"ok": False, "error": str(e), "trace": traceback.format_exc()}
