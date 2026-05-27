"""Reliable Windows launcher for Personal AI Shorts Studio."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
PORTS = [8000, 8001, 8002, 8003, 8004, 8005]


def main() -> int:
    if not PYTHON.exists():
        print("Python venv was not found.")
        print("Expected:")
        print(PYTHON)
        print("\nRun this first:")
        print("python -m venv .venv")
        print(".\\.venv\\Scripts\\activate")
        print("python -m pip install -r requirements.txt")
        return 1

    requested = os.getenv("PORT")
    ports = [int(requested)] if requested and requested.isdigit() else PORTS

    for port in ports:
        print("")
        print("=" * 72)
        print(f"Starting Personal AI Shorts Studio on http://127.0.0.1:{port}")
        print("Keep this window open while using the app.")
        print("=" * 72)

        env = _clean_env()
        env["PORT"] = str(port)
        env.setdefault("UVICORN_RELOAD", "false")

        code = subprocess.run([str(PYTHON), "main.py"], cwd=ROOT, env=env).returncode
        if code == 0:
            return 0

        print("")
        print(f"Port {port} did not start cleanly.")
        if requested:
            print("Because PORT was set manually, I will not try another port.")
            return code
        print("Trying the next local port...")

    print("")
    print("Could not start on ports 8000-8005.")
    print("If a port is busy, run:")
    print("netstat -ano | findstr :8000")
    print("Stop-Process -Id <PID_FROM_RIGHT_COLUMN> -Force")
    return 1


def _clean_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        if key.lower() == "path":
            env["PATH"] = value
        elif key not in env:
            env[key] = value
    env["PYTHONUNBUFFERED"] = "1"
    return env


if __name__ == "__main__":
    raise SystemExit(main())
