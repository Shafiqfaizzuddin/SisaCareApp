"""Exchange a validated Supabase login for a browser-session cookie."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials

from app.core.auth import AuthenticatedUser, authenticate_access_token, bearer_scheme
from app.core.config import Settings, get_settings
from app.repositories import browser_sessions
from app.repositories.reports import register_public_participant


router = APIRouter()
COOKIE = "sisacare_session"


@router.post("/session")
async def start_session(
    response: Response,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Sign in before creating a session.")
    user = await authenticate_access_token(credentials.credentials, settings)
    if not user["email_verified"]:
        raise HTTPException(status_code=403, detail="Confirm your email before signing in.")
    register_public_participant(user["id"], user["role"], user["email"])
    token = browser_sessions.create(user)
    response.set_cookie(COOKIE, token, httponly=True, secure=settings.session_cookie_secure,
                        samesite="lax", path="/")
    response.headers["Cache-Control"] = "no-store"
    return {"user_id": user["id"]}


@router.get("/session")
async def current_session(request: Request, response: Response) -> dict[str, str]:
    response.headers["Cache-Control"] = "no-store"
    token = request.cookies.get(COOKIE)
    user: AuthenticatedUser | None = browser_sessions.read(token) if token else None
    if user is None:
        raise HTTPException(status_code=401, detail="Your session has expired. Sign in again.")
    return {"user_id": user["id"], "role": user["role"], "email": user["email"],
            "display_name": user.get("display_name") or user["email"].split("@")[0] or "Member"}


@router.delete("/session", status_code=204)
async def end_session(request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        browser_sessions.revoke(token)
    response.delete_cookie(COOKIE, path="/", httponly=True, secure=get_settings().session_cookie_secure,
                           samesite="lax")
