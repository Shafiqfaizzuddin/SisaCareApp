"""Authenticated application proxy for the isolated loopback Florence service."""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.rate_limit import enforce_ai_analysis_rate_limit
from app.core.auth import AuthenticatedUser
from app.services.image_uploads import MAX_UPLOAD_SIZE


router = APIRouter()


def _proxy_failure(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={
        "success": False, "analysis_id": uuid4().hex,
        "image_width": None, "image_height": None,
        "model_id": None, "model_revision": None,
        "device": None, "precision": None,
        "detections": [], "processing_time_ms": 0,
        "warnings": [], "error": {"code": code, "message": message},
    })


@router.get("/health")
async def florence_health(
    _user: Annotated[AuthenticatedUser, Depends(enforce_ai_analysis_rate_limit)],
) -> JSONResponse:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.florence_service_url.rstrip('/')}/health")
        return JSONResponse(status_code=response.status_code, content=response.json())
    except (httpx.HTTPError, ValueError):
        return JSONResponse(status_code=503, content={
            "service_available": False, "model_ready": False,
            "device": None, "load_error": "Local Florence service is unavailable.",
        })


@router.post("/analyze")
async def analyze_with_florence(
    _user: Annotated[AuthenticatedUser, Depends(enforce_ai_analysis_rate_limit)],
    image: UploadFile = File(...),
) -> JSONResponse:
    settings = get_settings()
    if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        await image.close()
        return _proxy_failure(415, "UNSUPPORTED_IMAGE_TYPE", "Use a JPG, PNG, or WEBP image.")
    data = bytearray()
    try:
        while chunk := await image.read(min(1024 * 1024, MAX_UPLOAD_SIZE + 1 - len(data))):
            data.extend(chunk)
            if len(data) > MAX_UPLOAD_SIZE:
                return _proxy_failure(413, "IMAGE_TOO_LARGE", "Image exceeds the upload size limit.")
    finally:
        await image.close()
    try:
        async with httpx.AsyncClient(timeout=settings.florence_service_timeout_seconds) as client:
            response = await client.post(
                f"{settings.florence_service_url.rstrip('/')}/detect",
                files={"image": (image.filename or "image", bytes(data), image.content_type)},
            )
        return JSONResponse(status_code=response.status_code, content=response.json())
    except httpx.TimeoutException:
        return _proxy_failure(504, "FLORENCE_TIMEOUT", "Local Florence service timed out.")
    except (httpx.HTTPError, ValueError):
        return _proxy_failure(503, "FLORENCE_UNAVAILABLE", "Local Florence service is unavailable.")
