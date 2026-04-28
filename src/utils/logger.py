from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler


def get_logger(name: str = "you2") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        os.makedirs("logs", exist_ok=True)
        # Rotating file handler to keep logs bounded
        fh = RotatingFileHandler("logs/you2.log", maxBytes=5 * 1024 * 1024, backupCount=7, encoding="utf-8")
        fh.setLevel(logging.INFO)
        # Console output
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        logger.addHandler(fh)
        logger.addHandler(ch)
    return logger
