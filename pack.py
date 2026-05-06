#!/usr/bin/env python3
import sys
import platform
import subprocess
import os

def _build_windows():
    """Build for Windows."""
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "You2SocialBrain",
        "--onefile",
        "--console",
        "--add-data", f"src{os.pathsep}src",
        "--hidden-import", "flet",
        "--hidden-import", "flet_runtime",
        "--hidden-import", "sqlalchemy",
        "--hidden-import", "cryptography",
        "--hidden-import", "tweepy",
        "--hidden-import", "playwright",
        "--hidden-import", "requests_oauthlib",
        "--hidden-import", "apscheduler",
        "--hidden-import", "apscheduler.schedulers.background",
        "--hidden-import", "apscheduler.triggers.date",
        "--hidden-import", "apscheduler.triggers.cron",
        "--hidden-import", "numpy",
        "--hidden-import", "click",
        "--hidden-import", "tiktok_uploader",
        "--hidden-import", "db.database",
        "--hidden-import", "models",
        "--hidden-import", "brain.brain",
        "--hidden-import", "brain.ollama_bridge",
        "--hidden-import", "brain.generator",
        "--hidden-import", "brain.style_learner",
        "--hidden-import", "embeddings.vector_store",
        "--hidden-import", "x_api.x_client",
        "--hidden-import", "tiktok.tiktok_client",
        "--hidden-import", "platforms.x_poster",
        "--hidden-import", "platforms.tiktok_poster",
        "--hidden-import", "platforms.x_scraper",
        "--hidden-import", "platforms.tiktok_scraper",
        "--hidden-import", "platforms.x_reply_bot",
        "--hidden-import", "scheduler.scheduler",
        "--hidden-import", "encryption.crypto",
        "--hidden-import", "oauth.oauth_manager",
        "--hidden-import", "oauth.oauth_flow",
        "--hidden-import", "oauth.oauth_config",
        "--hidden-import", "utils.logger",
        "--hidden-import", "utils.audit",
        "--hidden-import", "utils.time_utils",
        "--hidden-import", "utils.error_handler",
        "--hidden-import", "utils.log_export",
        "--hidden-import", "config.settings",
        "--hidden-import", "prompts.prompt_builder",
        "--hidden-import", "ui.matrix_banner",
        "--hidden-import", "ui.dialogs",
        "--hidden-import", "security.token_store",
        "--hidden-import", "analytics.metrics",
        "--hidden-import", "image_gen.sd_client",
        "--hidden-import", "aiohttp",
        "--hidden-import", "logging.handlers",
        "--hidden-import", "packaging",
        "src/main.py"
    ]
    subprocess.run(cmd, check=True)

def _build_macos():
    """Build for macOS."""
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "You2SocialBrain",
        "--onefile",
        "--windowed",
        "--add-data", f"src{os.pathsep}src",
        "--hidden-import", "flet",
        "--hidden-import", "flet_runtime",
        "--hidden-import", "sqlalchemy",
        "--hidden-import", "cryptography",
        "--hidden-import", "tweepy",
        "--hidden-import", "playwright",
        "--hidden-import", "requests_oauthlib",
        "--hidden-import", "apscheduler",
        "--hidden-import", "numpy",
        "--hidden-import", "click",
        "--hidden-import", "analytics.metrics",
        "--hidden-import", "image_gen.sd_client",
        "src/main.py"
    ]
    subprocess.run(cmd, check=True)

def _build_linux():
    """Build for Linux."""
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "You2SocialBrain",
        "--onefile",
        "--console",
        "--add-data", f"src{os.pathsep}src",
        "--hidden-import", "flet",
        "--hidden-import", "flet_runtime",
        "--hidden-import", "sqlalchemy",
        "--hidden-import", "cryptography",
        "--hidden-import", "tweepy",
        "--hidden-import", "playwright",
        "--hidden-import", "requests_oauthlib",
        "--hidden-import", "apscheduler",
        "--hidden-import", "numpy",
        "--hidden-import", "click",
        "--hidden-import", "analytics.metrics",
        "--hidden-import", "image_gen.sd_client",
        "src/main.py"
    ]
    subprocess.run(cmd, check=True)

def main():
    system = platform.system().lower()
    if system in ("windows", "win32"):
        _build_windows()
    elif system == "darwin":
        _build_macos()
    else:
        _build_linux()

if __name__ == "__main__":
    main()
