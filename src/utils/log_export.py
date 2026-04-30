from __future__ import annotations

import os
from utils.time_utils import utc_now


EXPORT_DIR = os.path.join("logs", "exports")


def export_logs() -> str | None:
    os.makedirs(EXPORT_DIR, exist_ok=True)
    src = os.path.join("logs", "you2.log")
    if not os.path.exists(src):
        return None
    with open(src, "r", encoding="utf-8") as f:
        data = f.read()
    timestamp = utc_now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(EXPORT_DIR, f"you2_logs_{timestamp}.log")
    with open(out_path, "w", encoding="utf-8") as g:
        g.write(data)
    return out_path
