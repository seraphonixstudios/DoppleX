from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error
from typing import Optional, Dict
from packaging.version import Version, InvalidVersion
from utils.logger import get_logger

logger = get_logger("you2.updater")

GITHUB_API_URL = "https://api.github.com/repos/seraphonixstudios/DoppleX/releases/latest"
CURRENT_VERSION = "1.0.0"


class UpdateChecker:
    """Check for updates from GitHub releases."""
    
    def __init__(self, current_version: str = CURRENT_VERSION):
        self.current_version = current_version
        self.latest_version: Optional[str] = None
        self.download_url: Optional[str] = None
        self.release_notes: Optional[str] = None
    
    def check(self) -> Dict:
        """Check for updates. Returns dict with update info."""
        result = {
            "update_available": False,
            "current_version": self.current_version,
            "latest_version": None,
            "download_url": None,
            "release_notes": None,
            "error": None,
        }
        
        try:
            req = urllib.request.Request(
                GITHUB_API_URL,
                headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "You2SocialBrain/" + self.current_version},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            
            latest_tag = data.get("tag_name", "").lstrip("v")
            self.latest_version = latest_tag
            self.release_notes = data.get("body", "")
            
            result["latest_version"] = latest_tag
            result["release_notes"] = self.release_notes
            
            try:
                if Version(latest_tag) > Version(self.current_version):
                    result["update_available"] = True
                    # Find Windows asset
                    for asset in data.get("assets", []):
                        name = asset.get("name", "")
                        if name.endswith(".exe") and "windows" in name.lower():
                            result["download_url"] = asset.get("browser_download_url")
                            self.download_url = result["download_url"]
                            break
                    # Fallback: use release page
                    if not result["download_url"]:
                        result["download_url"] = data.get("html_url")
                        self.download_url = result["download_url"]
            except InvalidVersion:
                logger.warning("Could not parse version: %s", latest_tag)
                result["error"] = f"Could not parse version: {latest_tag}"
                
        except urllib.error.HTTPError as e:
            logger.error("GitHub API error: %s", e)
            result["error"] = f"GitHub API error: {e.code}"
        except Exception as e:
            logger.error("Update check failed: %s", e)
            result["error"] = str(e)
        
        return result
    
    def download_update(self, url: str, destination: str, progress_callback=None) -> bool:
        """Download update file to destination."""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "You2SocialBrain/" + self.current_version})
            
            with urllib.request.urlopen(req, timeout=120) as resp:
                total_size = int(resp.headers.get("content-length", 0))
                downloaded = 0
                chunk_size = 8192
                
                with open(destination, "wb") as f:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total_size > 0:
                            progress_callback(downloaded / total_size)
            
            logger.info("Update downloaded to %s", destination)
            return True
        except Exception as e:
            logger.error("Download failed: %s", e)
            return False


def check_for_updates() -> Dict:
    """Convenience function to check for updates."""
    checker = UpdateChecker()
    return checker.check()


def get_update_info_text(result: Dict) -> str:
    """Format update check result for display."""
    if result.get("error"):
        return f"Could not check for updates: {result['error']}"
    
    if result.get("update_available"):
        lines = [
            f"A new version is available!",
            f"Current: {result['current_version']}",
            f"Latest: {result['latest_version']}",
            "",
        ]
        if result.get("release_notes"):
            notes = result["release_notes"][:500]
            lines.append("Release Notes:")
            lines.append(notes)
        return "\n".join(lines)
    
    return f"You are up to date! (v{result['current_version']})"
