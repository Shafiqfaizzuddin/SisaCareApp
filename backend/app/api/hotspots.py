"""Read-only, administrator-only access to saved hotspot forecasts."""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from app.core.auth import AuthenticatedUser, require_admin_user
from app.repositories import forecasts

router = APIRouter()


@router.get("/forecasts")
async def forecast_list(
    admin: Annotated[AuthenticatedUser, Depends(require_admin_user)],
    provenance: Literal["production", "synthetic_demo"] = "production",
) -> dict:
    return await run_in_threadpool(forecasts.latest, provenance=provenance)
