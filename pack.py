#!/usr/bin/env python3
import sys
import platform
import subprocess
import os

def _build_window():
    cmd = [sys.executable, "-m", "PyInstaller", "--name", "you2", "--onefile", "src/main.py"]
    subprocess.run(cmd, check=True)

def _build_unix():
    cmd = [sys.executable, "-m", "PyInstaller", "--name", "you2", "--onefile", "src/main.py"]
    subprocess.run(cmd, check=True)

def main():
    system = platform.system().lower()
    if system in ("windows", "win32"):
        _build_window()
    else:
        _build_unix()

if __name__ == "__main__":
    main()
