import asyncio

import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.core.rate_limit import (
    enforce_ai_analysis_rate_limit,
    reset_ai_rate_limits,
)


def test_ai_rate_limit_is_enforced_per_authenticated_user() -> None:
    reset_ai_rate_limits()
    settings = Settings(
        _env_file=None,
        ai_rate_limit_requests=2,
        ai_rate_limit_window_seconds=60,
    )
    first_user = {"id": "user-1", "email": "one@example.com", "role": "user"}
    second_user = {"id": "user-2", "email": "two@example.com", "role": "user"}

    asyncio.run(enforce_ai_analysis_rate_limit(first_user, settings))
    asyncio.run(enforce_ai_analysis_rate_limit(first_user, settings))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(enforce_ai_analysis_rate_limit(first_user, settings))

    assert exc_info.value.status_code == 429
    assert "Retry-After" in (exc_info.value.headers or {})
    assert asyncio.run(
        enforce_ai_analysis_rate_limit(second_user, settings)
    ) == second_user
    reset_ai_rate_limits()
