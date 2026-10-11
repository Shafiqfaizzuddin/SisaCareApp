import asyncio

import httpx
import pytest
from fastapi import HTTPException

from app.core.auth import authenticate_access_token, require_admin_user, require_authenticated_user
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
                "email_confirmed_at": "2026-10-11T00:00:00Z",
                "identities": [{"provider": "email", "id": "admin-1"}],
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
        "email_verified": True,
        "google_sub": None,
        "google_email": None,
        "has_email_identity": True,
        "has_google_provider": False,
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


def test_unverified_email_cannot_participate() -> None:
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(require_authenticated_user({
            "id": "new-user", "email": "new@example.com", "role": "user",
            "email_verified": False, "google_sub": None, "has_email_identity": True,
            "google_email": None,
            "has_google_provider": False,
        }))
    assert exc_info.value.status_code == 403


def test_staff_email_and_claim_do_not_grant_admin() -> None:
    user = {
        "id": "staff-1", "email": "person@uitm.edu.my", "role": "user",
        "email_verified": True, "google_sub": None, "has_email_identity": True,
        "google_email": None,
        "has_google_provider": False,
    }
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(require_admin_user(user))
    assert exc_info.value.status_code == 403


def test_google_subject_is_read_from_provider_metadata_not_identity_row_id() -> None:
    async def authenticate() -> object:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={
                "id": "google-user", "email": "123@student.uitm.edu.my",
                "email_confirmed_at": "2026-10-11T00:00:00Z",
                "app_metadata": {"provider": "google", "providers": ["google"]},
                "identities": [{"provider": "google", "id": "identity-uuid",
                                "identity_data": {"sub": "stable-google-sub", "email": "123@student.uitm.edu.my"}}],
            })
        )) as client:
            return await authenticate_access_token("access-token", auth_settings(), client=client)
    user = asyncio.run(authenticate())
    assert user["google_sub"] == "stable-google-sub"
    assert user["role"] == "user"
