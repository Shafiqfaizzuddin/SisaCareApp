"""Small in-process rate limiter for expensive local AI analysis requests."""

from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import monotonic
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.core.auth import AuthenticatedUser, require_authenticated_user
from app.core.config import Settings, get_settings


_attempts: defaultdict[str, deque[float]] = defaultdict(deque)
_lock = Lock()


def reset_ai_rate_limits() -> None:
    """Clear process-local limiter state, primarily for isolated tests."""

    with _lock:
        _attempts.clear()


async def enforce_ai_analysis_rate_limit(
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthenticatedUser:
    now = monotonic()
    window = settings.ai_rate_limit_window_seconds
    cutoff = now - window

    with _lock:
        user_attempts = _attempts[user["id"]]
        while user_attempts and user_attempts[0] <= cutoff:
            user_attempts.popleft()
        if len(user_attempts) >= settings.ai_rate_limit_requests:
            retry_after = max(1, int(user_attempts[0] + window - now) + 1)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many analysis requests. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )
        user_attempts.append(now)

    return user


__all__ = ["enforce_ai_analysis_rate_limit", "reset_ai_rate_limits"]
