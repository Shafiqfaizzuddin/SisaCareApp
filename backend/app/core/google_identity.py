"""Server verification of Google ID tokens used for Supabase sign-in."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2 import id_token

from app.core.config import Settings


ALLOWED_GOOGLE_DOMAINS = frozenset({"uitm.edu.my", "student.uitm.edu.my"})


def normalized_email_domain(email: str) -> str:
    parts = email.strip().casefold().split("@")
    return parts[1] if len(parts) == 2 and parts[0] and parts[1] else ""


def suggested_matric(email: str) -> str | None:
    normalized = email.strip().casefold()
    if normalized_email_domain(normalized) != "student.uitm.edu.my":
        return None
    prefix = normalized.split("@", 1)[0]
    return prefix if prefix and prefix.isascii() and prefix.isdecimal() else None


def verify_google_token(token: str, settings: Settings) -> dict[str, str]:
    if not settings.google_client_id.strip():
        raise HTTPException(status_code=503, detail="Google sign-in is not configured.")
    try:
        claims: dict[str, Any] = id_token.verify_oauth2_token(
            token, Request(), settings.google_client_id.strip()
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid Google identity token.") from exc
    except GoogleAuthError as exc:
        raise HTTPException(status_code=503, detail="Google verification is unavailable.") from exc
    email = claims.get("email")
    sub = claims.get("sub")
    if not isinstance(email, str) or not isinstance(sub, str) or not sub:
        raise HTTPException(status_code=401, detail="Google identity is incomplete.")
    if claims.get("email_verified") is not True:
        raise HTTPException(status_code=403, detail="Google email is not verified.")
    if normalized_email_domain(email) not in ALLOWED_GOOGLE_DOMAINS:
        raise HTTPException(status_code=403, detail="Use a verified UiTM Google account.")
    return {"email": email.strip().casefold(), "sub": sub}


async def ensure_no_automatic_link(
    email: str, sub: str, settings: Settings,
    *, client: httpx.AsyncClient | None = None,
) -> str | None:
    """Resolve Google subject first; reserve same-email collisions for website accounts."""
    secret = settings.supabase_service_role_key.get_secret_value().strip()
    if not secret or not settings.supabase_url:
        raise HTTPException(status_code=503, detail="Google account checks are not configured.")
    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=10.0)
    headers = {"apikey": secret, "Authorization": f"Bearer {secret}"}

    def google_identity_matches(user: dict[str, Any]) -> bool:
        identities = user.get("identities")
        return isinstance(identities, list) and any(
            isinstance(identity, dict)
            and identity.get("provider") == "google"
            and (identity.get("provider_id") == sub or
                 isinstance(identity.get("identity_data"), dict)
                 and identity["identity_data"].get("sub") == sub)
            for identity in identities
        )

    def google_only_recovery(user: dict[str, Any]) -> bool:
        identities = user.get("identities")
        metadata = user.get("app_metadata")
        return (
            isinstance(identities, list)
            and not any(isinstance(item, dict) and item.get("provider") in {"email", "google"} for item in identities)
            and isinstance(metadata, dict) and metadata.get("provider") == "google"
            and (metadata.get("provider_id") == sub or metadata.get("google_sub") == sub)
        )

    async def detail(user_id: str) -> dict[str, Any]:
        try:
            response = await active_client.get(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{user_id}",
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(status_code=503, detail="Account check is unavailable.") from exc
        result = payload.get("user", payload) if isinstance(payload, dict) else None
        if not isinstance(result, dict) or result.get("id") != user_id or not isinstance(result.get("identities"), list):
            raise HTTPException(status_code=503, detail="Account check is unavailable.")
        return result

    try:
        # A completed local association is a fast hint, checked against Supabase's
        # trusted provider record before a new Supabase session is requested.
        from app.repositories.identities import google_owner_id

        known_id = google_owner_id(sub)
        if known_id:
            known = await detail(known_id)
            if google_identity_matches(known):
                return known_id

        email_collision: dict[str, Any] | None = None
        for page in range(1, 101):
            try:
                response = await active_client.get(
                    f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users",
                    params={"page": page, "per_page": 1000},
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise HTTPException(status_code=503, detail="Account check is unavailable.") from exc
            users = payload.get("users") if isinstance(payload, dict) else None
            if not isinstance(users, list):
                raise HTTPException(status_code=503, detail="Account check is unavailable.")
            for user in users:
                if not isinstance(user, dict):
                    continue
                user_id = user.get("id")
                if not isinstance(user_id, str):
                    continue
                if google_identity_matches(user):
                    return user_id
                if str(user.get("email", "")).strip().casefold() == email:
                    email_collision = await detail(user_id)
                    if google_identity_matches(email_collision):
                        return user_id
            if len(users) < 1000:
                break
        else:
            raise HTTPException(status_code=503, detail="Account check is unavailable.")
        if email_collision is not None:
            if google_only_recovery(email_collision):
                # Completion still requires a Supabase session carrying this exact
                # Google subject before the local association is persisted.
                return email_collision["id"]
            raise HTTPException(
                status_code=409,
                detail="An account already uses this email. Sign in to that account and connect Google, or request an email sign-in link if you do not have a password.",
            )
        return None
    finally:
        if owns_client:
            await active_client.aclose()
