"""Async subprocess utilities for local command-line tools."""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)


class ToolExecutionError(RuntimeError):
    """Raised when a required local command fails."""

    def __init__(self, command: Sequence[str], returncode: int, stderr: str) -> None:
        self.command = list(command)
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(
            f"Command failed with exit code {returncode}: {shlex.join(command)}\n{stderr}"
        )


@dataclass(frozen=True)
class CommandResult:
    """Result returned by a subprocess call."""

    stdout: str
    stderr: str
    returncode: int


async def run_command(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout_seconds: int | None = None,
) -> CommandResult:
    """Run a command and raise ToolExecutionError on non-zero exit."""

    resolved_command, env = _prepare_command(command)
    logger.info("Running command: %s", shlex.join(resolved_command))
    process = await asyncio.create_subprocess_exec(
        *resolved_command,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_seconds,
        )
    except TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise TimeoutError(f"Command timed out: {shlex.join(resolved_command)}") from exc

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    if process.returncode != 0:
        logger.error("Command failed: %s", stderr.strip())
        raise ToolExecutionError(resolved_command, process.returncode or 1, stderr)
    if stderr.strip():
        logger.debug("Command stderr: %s", stderr.strip())
    return CommandResult(stdout=stdout, stderr=stderr, returncode=process.returncode or 0)


def _prepare_command(command: Sequence[str]) -> tuple[list[str], dict[str, str]]:
    """Resolve project-local CLI tools before launching a subprocess."""

    env = os.environ.copy()
    env["PATH"] = _runtime_path(env.get("PATH", ""))
    resolved = list(command)
    if not resolved:
        return resolved, env

    executable = resolved[0]
    if Path(executable).is_absolute():
        return resolved, env

    found = shutil.which(executable, path=env["PATH"])
    if found:
        resolved[0] = found
        return resolved, env

    if executable.lower() in {"ffmpeg", "ffmpeg.exe"}:
        try:
            import imageio_ffmpeg

            resolved[0] = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            pass
    return resolved, env


def _runtime_path(current_path: str) -> str:
    """Prepend the active or project virtualenv Scripts directory to PATH."""

    project_root = Path(__file__).resolve().parents[2]
    candidates = [
        Path(sys.executable).resolve().parent,
        project_root / ".venv" / "Scripts",
        project_root / ".venv" / "bin",
    ]
    parts = [str(path) for path in candidates if path.exists()]
    parts.append(current_path)
    return os.pathsep.join(dict.fromkeys(part for part in parts if part))
