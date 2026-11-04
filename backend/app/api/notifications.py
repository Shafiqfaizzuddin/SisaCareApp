"""Private administrator delivery monitoring and explicit failed-event retry."""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from app.core.auth import AuthenticatedUser, require_admin_user
from app.core.config import get_settings
from app.repositories.reports import list_report_email_deliveries, retry_failed_report_email
from app.services.report_email import channel_ready

router = APIRouter()
Admin = Annotated[AuthenticatedUser, Depends(require_admin_user)]


@router.get("/email")
async def email_delivery_status(_admin: Admin,
    status: Literal["queued", "retrying", "sent", "failed"] | None = None,
    limit: int = Query(default=100, ge=1, le=200)) -> dict:
    rows = await run_in_threadpool(list_report_email_deliveries, status=status, limit=limit)
    settings = get_settings()
    return {"delivery_configured": {"admin": channel_ready(settings, "admin"),
                                     "citizen": channel_ready(settings, "user")},
            "events": rows}


@router.post("/email/{event_key}/retry")
async def retry_email(event_key: str, _admin: Admin) -> dict:
    if len(event_key) > 200:
        raise HTTPException(422, "Invalid event key.")
    if not await run_in_threadpool(retry_failed_report_email, event_key):
        raise HTTPException(409, "Only exhausted, unsent notifications can be retried.")
    return {"event_key": event_key, "delivery_status": "queued"}
