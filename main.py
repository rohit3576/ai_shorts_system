"""Application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path
import socket
import subprocess

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import router as api_router
from app.config import settings
from app.dashboard.routes import router as dashboard_router
from app.importer.artifacts import ArtifactImporter
from app.logging_config import setup_logging
from app.scheduler.service import AppScheduler
from database.init_db import init_db

scheduler = AppScheduler()
HOST = "127.0.0.1"
PORT = int(os.getenv("PORT", "8000"))
RELOAD = os.getenv("UVICORN_RELOAD", "false").lower() in {"1", "true", "yes"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize local runtime dependencies."""

    setup_logging(settings.log_level)
    settings.ensure_directories()
    await init_db()
    await ArtifactImporter().import_existing()
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(api_router)
app.include_router(dashboard_router)
app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).parent / "app" / "dashboard" / "static")),
    name="static",
)
app.mount(
    "/media",
    StaticFiles(directory=str(settings.resolve_path(settings.data_dir))),
    name="media",
)


def _port_process_ids(port: int) -> list[str]:
    """Return Windows PIDs listening on a local TCP port."""

    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except Exception:
        return []

    pids: list[str] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].upper() != "TCP":
            continue
        local_address, state, pid = parts[1], parts[-2].upper(), parts[-1]
        if state == "LISTENING" and local_address.endswith(f":{port}") and pid.isdigit() and pid not in pids:
            pids.append(pid)
    return pids


def _print_port_help(port: int, error: OSError | None = None) -> None:
    pids = _port_process_ids(port)
    print("\nPersonal AI Shorts Studio could not start.")
    if error:
        print(f"Socket error: {error}")
    print(f"Port {port} is busy or blocked.\n")
    if pids:
        print("Copy-paste this in PowerShell, then run python main.py again:")
        print(f"Stop-Process -Id {','.join(pids)} -Force")
    else:
        print("Copy-paste this in PowerShell to find the PID, then stop it:")
        print(f"netstat -ano | findstr :{port}")
        print("Stop-Process -Id <PID_FROM_RIGHT_COLUMN> -Force")
    print("\nAlternative temporary port:")
    print("$env:PORT=8001")
    print("python main.py\n")


def _ensure_port_available(host: str, port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        if sock.connect_ex((host, port)) == 0:
            _print_port_help(port)
            raise SystemExit(1)


if __name__ == "__main__":
    _ensure_port_available(HOST, PORT)
    uvicorn.run("main:app", host=HOST, port=PORT, reload=RELOAD)
