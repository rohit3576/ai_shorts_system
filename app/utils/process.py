"""Async subprocess utilities for local command-line tools."""

from __future__ import annotations

import asyncio
import logging
import shlex
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

    logger.info("Running command: %s", shlex.join(command))
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(cwd) if cwd else None,
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
        raise TimeoutError(f"Command timed out: {shlex.join(command)}") from exc

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    if process.returncode != 0:
        logger.error("Command failed: %s", stderr.strip())
        raise ToolExecutionError(command, process.returncode or 1, stderr)
    if stderr.strip():
        logger.debug("Command stderr: %s", stderr.strip())
    return CommandResult(stdout=stdout, stderr=stderr, returncode=process.returncode or 0)

