"""Small retry helpers for flaky local commands and network requests."""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")

logger = logging.getLogger(__name__)


def async_retry(
    *,
    attempts: int = 3,
    backoff_seconds: float = 1.5,
    retry_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Retry an async function with exponential backoff."""

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_error: Exception | None = None
            for attempt in range(1, attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except retry_exceptions as exc:
                    last_error = exc
                    if attempt >= attempts:
                        break
                    sleep_for = backoff_seconds * (2 ** (attempt - 1))
                    logger.warning(
                        "%s failed on attempt %s/%s: %s. Retrying in %.1fs",
                        func.__name__,
                        attempt,
                        attempts,
                        exc,
                        sleep_for,
                    )
                    await asyncio.sleep(sleep_for)
            assert last_error is not None
            raise last_error

        return wrapper

    return decorator

