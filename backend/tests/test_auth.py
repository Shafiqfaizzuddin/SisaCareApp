import asyncio

import httpx
import pytest
from fastapi import HTTPException

from app.core.auth import authenticate_access_token
from app.core.config import Settings


def auth_settings() -> Settings:
    return Settings(
        _env_file=None,
        supabase_url="https://example.supabase.co",
        supabase_publishable_key="publishable-key",
    )


def test_supabase_token_returns_trusted_user_identity() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://example.supabase.co/auth/v1/user"
        assert request.headers["authorization"] == "Bearer access-token"
        assert request.headers["apikey"] == "publishable-key"
        return httpx.Response(
            200,
            json={
                "id": "admin-1",
                "email": "admin@example.com",
                "app_metadata": {"role": "admin"},
            },
        )

    async def authenticate() -> object:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            return await authenticate_access_token(
                "access-token",
                auth_settings(),
                client=client,
            )

    user = asyncio.run(authenticate())

    assert user == {
        "id": "admin-1",
        "email": "admin@example.com",
        "role": "admin",
    }


def test_invalid_supabase_token_is_rejected_without_provider_detail() -> None:
    async def authenticate() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    401,
                    json={"message": "token detail"},
                )
            )
        ) as client:
            await authenticate_access_token(
                "invalid-token",
                auth_settings(),
                client=client,
            )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(authenticate())

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Authentication is required."
