#!/usr/bin/env python3
import sys
import platform
import subprocess
import os
from pathlib import Path

def _get_assets():
    """Get platform-specific assets to bundle."""
    assets = []
    src_dir = Path("src")
    # Add all Python files
    for py_file in src_dir.rglob("*.py"):
        assets.append(str(py_file))
    # Add requirements
    if Path("requirements.txt").exists():
        assets.append("requirements.txt")
    return assets

def _build_windows():
    """Build for Windows."""
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "DoppleX",
        "--onefile",
        "--console",
        "--add-data", f"src{os.pathsep}src",
        "--hidden-import", "flet",
        "--hidden-import", "sqlalchemy",
        "--hidden-import", "cryptography",
        "--hidden-import", "tweepy",
        "--hidden-import", "playwright",
        "src/main.py"
    ]
    subprocess.run(cmd, check=True)

def _build_macos():
    """Build for macOS."""
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "DoppleX",
        "--onefile",
        "--windowed",
        "--add-data", f"src{os.pathsep}src",
        "--hidden-import", "flet",
        "--hidden-import", "sqlalchemy",
        "--hidden-import", "cryptography",
        "--hidden-import", "tweepy",
        "--hidden-import", "playwright",
        "src/main.py"
    ]
    subprocess.run(cmd, check=True)

def _build_linux():
    """Build for Linux."""
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "DoppleX",
        "--onefile",
        "--console",
        "--add-data", f"src{os.pathsep}src",
        "--hidden-import", "flet",
        "--hidden-import", "sqlalchemy",
        "--hidden-import", "cryptography",
        "--hidden-import", "tweepy",
        "--hidden-import", "playwright",
        "src/main.py"
    ]
    subprocess.run(cmd, check=True)

def main():
    system = platform.system().lower()
    if system in ("windows", "win32"):
        _build_windows()
    elif system == "darwin":
        _build_macos()
    else:  # Linux and others
        _build_linux()

if __name__ == "__main__":
    main()
