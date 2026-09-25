"""Supabase-backed authentication dependencies for protected API routes."""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings


class AuthenticatedUser(TypedDict):
    id: str
    email: str
    role: Literal["user", "admin"]


bearer_scheme = HTTPBearer(auto_error=False)


async def authenticate_access_token(
    token: str,
    settings: Settings,
    *,
    client: httpx.AsyncClient | None = None,
) -> AuthenticatedUser:
    """Validate a Supabase access token and return trusted identity claims."""

    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is not configured.",
        )

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=10.0)
    try:
        try:
            response = await active_client.get(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
                headers={
                    "apikey": settings.supabase_publishable_key,
                    "Authorization": f"Bearer {token}",
                },
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service is temporarily unavailable.",
            ) from exc
    finally:
        if owns_client:
            await active_client.aclose()

    if response.status_code in {401, 403}:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if response.is_error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is temporarily unavailable.",
        )

    try:
        payload: Any = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service returned an invalid response.",
        ) from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("id"), str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    app_metadata = payload.get("app_metadata")
    role = (
        "admin"
        if isinstance(app_metadata, dict) and app_metadata.get("role") == "admin"
        else "user"
    )
    email = payload.get("email")
    return {
        "id": payload["id"],
        "email": email if isinstance(email, str) else "",
        "role": role,
    }


async def get_optional_authenticated_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthenticatedUser | None:
    if credentials is None:
        return None
    return await authenticate_access_token(credentials.credentials, settings)


async def require_authenticated_user(
    user: Annotated[
        AuthenticatedUser | None,
        Depends(get_optional_authenticated_user),
    ],
) -> AuthenticatedUser:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def require_admin_user(
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> AuthenticatedUser:
    if user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access is required.",
        )
    return user


__all__ = [
    "AuthenticatedUser",
    "authenticate_access_token",
    "get_optional_authenticated_user",
    "require_admin_user",
    "require_authenticated_user",
]
