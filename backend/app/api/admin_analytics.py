"""Administrator-only aggregated analytics and privacy-limited exports."""
from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from app.core.auth import AuthenticatedUser, require_admin_user
from app.services.admin_analytics import Filters, csv_export, snapshot
from app.services.analytics_pdf import render_pdf

router = APIRouter()
Admin = Annotated[AuthenticatedUser, Depends(require_admin_user)]


def requested_filters(
    start: date | None = None, end: date | None = None,
    category: str | None = Query(default=None, max_length=100),
    status: str | None = Query(default=None, max_length=50),
    area: str | None = Query(default=None, max_length=40),
    provenance: Literal["production", "legacy_unknown", "demo"] = "production",
) -> Filters:
    try:
        return Filters(start=start, end=end, category=category, status=status, area=area, provenance=provenance)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


FiltersParam = Annotated[Filters, Depends(requested_filters)]


@router.get("")
async def analytics(_admin: Admin, filters: FiltersParam) -> dict:
    result = await run_in_threadpool(snapshot, filters)
    result.pop("reports")
    return result


@router.get("/export.csv")
async def export_csv(_admin: Admin, filters: FiltersParam) -> Response:
    data = await run_in_threadpool(snapshot, filters)
    content = await run_in_threadpool(csv_export, data)
    return Response(content, media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": 'attachment; filename="sisacare-analytics.csv"',
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/export.pdf")
async def export_pdf(_admin: Admin, filters: FiltersParam) -> Response:
    data = await run_in_threadpool(snapshot, filters)
    content = await run_in_threadpool(render_pdf, data)
    return Response(content, media_type="application/pdf", headers={
        "Content-Disposition": 'attachment; filename="sisacare-analytics.pdf"',
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
