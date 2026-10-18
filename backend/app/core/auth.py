"""Supabase-backed authentication dependencies for protected API routes."""

from __future__ import annotations

from typing import Annotated, Any, Literal, NotRequired, TypedDict

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings


class AuthenticatedUser(TypedDict):
    id: str
    email: str
    role: Literal["user", "admin"]
    email_verified: bool
    google_sub: str | None
    google_email: str | None
    has_email_identity: bool
    has_google_provider: bool
    claimed_affiliation: NotRequired[Literal["student", "staff"] | None]
    display_name: NotRequired[str]


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
    providers = app_metadata.get("providers") if isinstance(app_metadata, dict) else None
    has_google_provider = (
        isinstance(app_metadata, dict) and app_metadata.get("provider") == "google"
    ) or (isinstance(providers, list) and "google" in providers)
    role = (
        "admin"
        if isinstance(app_metadata, dict) and app_metadata.get("role") == "admin"
        else "user"
    )
    email = payload.get("email")
    verified = bool(payload.get("email_confirmed_at"))
    identities = payload.get("identities")
    user_metadata = payload.get("user_metadata")
    claim = user_metadata.get("claimed_affiliation") if isinstance(user_metadata, dict) else None
    google_sub = None
    google_email = None
    has_email_identity = False
    if isinstance(identities, list):
        for identity in identities:
            if not isinstance(identity, dict):
                continue
            if identity.get("provider") == "email":
                has_email_identity = True
            if identity.get("provider") == "google":
                identity_data = identity.get("identity_data")
                candidate = identity.get("provider_id")
                if not isinstance(candidate, str) and isinstance(identity_data, dict):
                    candidate = identity_data.get("sub")
                if isinstance(candidate, str):
                    google_sub = candidate
                    if isinstance(identity_data, dict) and isinstance(identity_data.get("email"), str):
                        google_email = identity_data["email"]
                    break
    authenticated_user: AuthenticatedUser = {
        "id": payload["id"],
        "email": email if isinstance(email, str) else "",
        "role": role,
        "email_verified": verified,
        "google_sub": google_sub,
        "google_email": google_email,
        "has_email_identity": has_email_identity,
        "has_google_provider": has_google_provider,
    }
    if isinstance(user_metadata, dict):
        name = user_metadata.get("full_name") or user_metadata.get("name")
        if isinstance(name, str) and name.strip():
            authenticated_user["display_name"] = name.strip()[:120]
    if claim in {"student", "staff"}:
        authenticated_user["claimed_affiliation"] = claim
    return authenticated_user


async def get_optional_authenticated_user(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthenticatedUser | None:
    cookie = request.cookies.get("sisacare_session")
    if cookie:
        from app.repositories.browser_sessions import read

        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            allowed = set(settings.allowed_cors_origins) | {str(request.base_url).rstrip("/")}
            if origin is not None and origin not in allowed:
                raise HTTPException(status_code=403, detail="Invalid session request origin.")
        user = read(cookie)
        if user is None:
            raise HTTPException(status_code=401, detail="Your session has expired. Sign in again.")
        return user
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
    if not user["email_verified"]:
        raise HTTPException(status_code=403, detail="Confirm your email before participating.")
    if user["has_google_provider"] and not user["google_sub"]:
        raise HTTPException(status_code=403, detail="Google identity details are unavailable.")
    if user["google_sub"] is not None:
        from app.repositories.identities import has_google_sub
        if not has_google_sub(user["id"], user["google_sub"]):
            raise HTTPException(status_code=403, detail="Complete Google sign-in verification.")
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
