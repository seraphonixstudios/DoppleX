from __future__ import annotations

import sys
import threading
from typing import Callable, Optional

from utils.logger import get_logger

logger = get_logger("you2.tray")

# Guard optional dependency
try:
    import pystray
    from PIL import Image, ImageDraw
    PYSTRAY_AVAILABLE = True
except Exception:
    pystray = None  # type: ignore
    Image = None  # type: ignore
    ImageDraw = None  # type: ignore
    PYSTRAY_AVAILABLE = False


def _create_icon_image(size: int = 64) -> "Image.Image":
    """Generate a simple green circle icon for the tray."""
    if Image is None or ImageDraw is None:
        raise RuntimeError("PIL not available")
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = size // 8
    draw.ellipse([margin, margin, size - margin, size - margin], fill=(57, 255, 20, 255))
    return img


class TrayManager:
    """Manages the system tray icon for background operation."""

    def __init__(self, on_show: Callable, on_exit: Callable):
        self.on_show = on_show
        self.on_exit = on_exit
        self.icon: Optional[pystray.Icon] = None
        self._thread: Optional[threading.Thread] = None

    def is_available(self) -> bool:
        return PYSTRAY_AVAILABLE

    def start(self) -> bool:
        """Start the tray icon in a background thread."""
        if not PYSTRAY_AVAILABLE:
            logger.warning("pystray not installed. GUI will exit on close.")
            return False

        try:
            menu = pystray.Menu(
                pystray.MenuItem("Show You2.0", self._handle_show),
                pystray.MenuItem("Status", self._handle_status),
                pystray.MenuItem("Exit", self._handle_exit),
            )
            self.icon = pystray.Icon(
                "you2",
                icon=_create_icon_image(),
                title="You2.0 Social Brain",
                menu=menu,
            )
            self._thread = threading.Thread(target=self.icon.run, daemon=True)
            self._thread.start()
            logger.info("System tray started")
            return True
        except Exception as e:
            logger.error("Failed to start tray: %s", e)
            return False

    def stop(self):
        """Stop the tray icon."""
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None

    def notify(self, title: str, message: str):
        """Show a tray notification."""
        if self.icon and self.icon.visible:
            try:
                self.icon.notify(message, title)
            except Exception as e:
                logger.debug("Notification failed: %s", e)

    def _handle_show(self, icon, item):
        self.on_show()

    def _handle_status(self, icon, item):
        from db.database import SessionLocal
        from models import ScheduledPost, Account
        try:
            with SessionLocal() as db:
                scheduled = db.query(ScheduledPost).filter(ScheduledPost.status == "scheduled").count()
                accounts = db.query(Account).count()
            self.notify("You2.0 Status", f"Accounts: {accounts} | Scheduled: {scheduled}")
        except Exception:
            self.notify("You2.0 Status", "Running in background")

    def _handle_exit(self, icon, item):
        self.icon.stop()
        self.on_exit()
