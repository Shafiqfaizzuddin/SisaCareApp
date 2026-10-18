"""Authenticated member dashboard API."""

from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.core.auth import AuthenticatedUser, require_authenticated_user
from app.repositories.reports import get_member_dashboard, get_own_report_tracking


router = APIRouter()


@router.get("/leaderboard")
async def read_leaderboard(limit: int = 50, offset: int = 0) -> dict[str, Any]:
    raise HTTPException(status_code=410, detail="The legacy leaderboard is retired pending a community incentive policy.")


@router.get("/me/dashboard")
async def read_member_dashboard(
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> dict[str, Any]:
    if user["role"] != "user":
        raise HTTPException(
            status_code=403,
            detail="Community User access is required.",
        )

    try:
        return await run_in_threadpool(get_member_dashboard, user["id"])
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(
            status_code=500,
            detail="Member dashboard data is temporarily unavailable.",
        ) from exc


@router.get("/me/reports/{report_id}")
async def read_own_report(
    report_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> dict[str, Any]:
    if user["role"] != "user":
        raise HTTPException(status_code=403, detail="Community User access is required.")
    report = await run_in_threadpool(get_own_report_tracking, report_id, user["id"])
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    return report


__all__ = ["router"]
