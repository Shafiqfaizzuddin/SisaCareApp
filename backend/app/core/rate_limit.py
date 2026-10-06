"""Small in-process rate limiter for expensive local AI analysis requests."""

from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import monotonic
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.core.auth import AuthenticatedUser, require_authenticated_user
from app.core.config import Settings, get_settings


_attempts: defaultdict[str, deque[float]] = defaultdict(deque)
_location_attempts: defaultdict[str, deque[float]] = defaultdict(deque)
_lock = Lock()


def reset_ai_rate_limits() -> None:
    """Clear process-local limiter state, primarily for isolated tests."""

    with _lock:
        _attempts.clear()


def reset_location_rate_limits() -> None:
    """Clear process-local location limiter state for isolated tests."""

    with _lock:
        _location_attempts.clear()


def _enforce_limit(
    attempts: defaultdict[str, deque[float]],
    key: str,
    *,
    request_limit: int,
    window: int,
    message: str,
) -> None:
    now = monotonic()
    cutoff = now - window

    with _lock:
        key_attempts = attempts[key]
        while key_attempts and key_attempts[0] <= cutoff:
            key_attempts.popleft()
        if len(key_attempts) >= request_limit:
            retry_after = max(1, int(key_attempts[0] + window - now) + 1)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=message,
                headers={"Retry-After": str(retry_after)},
            )
        key_attempts.append(now)


async def enforce_ai_analysis_rate_limit(
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthenticatedUser:
    _enforce_limit(
        _attempts,
        user["id"],
        request_limit=settings.ai_rate_limit_requests,
        window=settings.ai_rate_limit_window_seconds,
        message="Too many analysis requests. Please try again later.",
    )

    return user


async def enforce_location_rate_limit(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    client_host = request.client.host if request.client else "unknown"
    _enforce_limit(
        _location_attempts,
        client_host,
        request_limit=settings.location_rate_limit_requests,
        window=settings.location_rate_limit_window_seconds,
        message="Too many location requests. Please try again later.",
    )


__all__ = [
    "enforce_ai_analysis_rate_limit",
    "enforce_location_rate_limit",
    "reset_ai_rate_limits",
    "reset_location_rate_limits",
]
