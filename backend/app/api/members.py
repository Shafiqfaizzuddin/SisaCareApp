"""Authenticated member dashboard API."""

from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.core.auth import AuthenticatedUser, require_authenticated_user
from app.repositories.reports import get_member_dashboard


router = APIRouter()


@router.get("/me/dashboard")
async def read_member_dashboard(
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> dict[str, Any]:
    if user["role"] != "user":
        raise HTTPException(
            status_code=403,
            detail="Member access is required.",
        )

    try:
        return await run_in_threadpool(get_member_dashboard, user["id"])
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(
            status_code=500,
            detail="Member dashboard data is temporarily unavailable.",
        ) from exc


__all__ = ["router"]
