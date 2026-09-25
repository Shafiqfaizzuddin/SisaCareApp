"""HTTP boundary for temporary waste-image analysis."""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path
from time import perf_counter
from typing import Annotated, Any
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse

from app.core.auth import AuthenticatedUser, require_authenticated_user
from app.core.config import get_settings
from app.core.rate_limit import enforce_ai_analysis_rate_limit
from app.services.ai import analyze_waste_image
from app.services.ai.image_annotator import ANNOTATED_OUTPUT_DIR
from app.services.ai.image_validation import ImageValidationError, validate_image
from app.repositories.reports import (
    analysis_draft_asset_belongs_to_user,
    create_analysis_draft,
)
from app.services.image_uploads import (
    MAX_UPLOAD_SIZE,
    UPLOAD_CHUNK_SIZE,
    UploadMetadataError,
    create_unique_upload_path,
    save_image_upload,
    upload_size_limit_message,
    validate_image_upload_metadata,
)


logger = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_DIR = get_settings().upload_dir
TEMP_MEDIA_HEADERS = {
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
}
UPLOAD_FILENAME_PATTERN = re.compile(r"^upload-[0-9a-f]{32}\.(?:jpg|png|webp)$")
ANNOTATED_FILENAME_PATTERN = re.compile(r"^annotated-[0-9a-f]{32}\.jpg$")
MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def _log_analysis_failure(
    request_id: str,
    code: str,
    started_at: float,
    *,
    level: int = logging.WARNING,
) -> None:
    logger.log(
        level,
        "analysis_request_failed request_id=%s code=%s duration_ms=%d",
        request_id,
        code,
        round((perf_counter() - started_at) * 1000),
    )


def _failure_status(code: str) -> int:
    if code == "NO_WASTE_DETECTED":
        return 422
    if code in {
        "IMAGE_NOT_FOUND",
        "INVALID_IMAGE",
        "UNSUPPORTED_FILE_TYPE",
        "INVALID_CONFIDENCE_THRESHOLD",
        "INVALID_DETECTION_DATA",
    }:
        return 400
    if code == "OLLAMA_TIMEOUT":
        return 504
    if code in {
        "OLLAMA_UNAVAILABLE",
        "OLLAMA_MODEL_NOT_INSTALLED",
        "OLLAMA_API_ERROR",
        "INVALID_OLLAMA_RESPONSE",
    }:
        return 502
    return 500


def _annotated_image_url(path: str) -> str:
    resolved_path = Path(path).resolve()
    annotated_root = ANNOTATED_OUTPUT_DIR.resolve()
    try:
        relative_path = resolved_path.relative_to(annotated_root)
    except ValueError as exc:
        raise ValueError(
            "Annotated image was created outside the output directory."
        ) from exc

    return f"/api/waste/annotated/{quote(relative_path.as_posix())}"


def _temporary_media_path(
    root: Path,
    filename: str,
    pattern: re.Pattern[str],
) -> Path:
    if not pattern.fullmatch(filename):
        raise HTTPException(status_code=404, detail="Image not found.")
    resolved_root = root.resolve()
    candidate = (resolved_root / filename).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Image not found.") from exc
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Image not found.")
    return candidate


def _remove_temporary_file(path: str | Path, root: Path) -> None:
    try:
        resolved_root = root.resolve()
        candidate = Path(path).resolve()
        candidate.relative_to(resolved_root)
        candidate.unlink(missing_ok=True)
    except (OSError, ValueError):
        return


@router.get("/uploads/{filename}", response_class=FileResponse)
async def read_uploaded_image(
    filename: str,
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> FileResponse:
    path = _temporary_media_path(UPLOAD_DIR, filename, UPLOAD_FILENAME_PATTERN)
    owns_asset = await run_in_threadpool(
        analysis_draft_asset_belongs_to_user,
        user["id"],
        path,
    )
    if not owns_asset:
        raise HTTPException(status_code=404, detail="Image not found.")
    return FileResponse(
        path,
        media_type=MEDIA_TYPES[path.suffix.lower()],
        headers=TEMP_MEDIA_HEADERS,
    )


@router.get("/annotated/{filename}", response_class=FileResponse)
async def read_annotated_image(
    filename: str,
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> FileResponse:
    path = _temporary_media_path(
        ANNOTATED_OUTPUT_DIR,
        filename,
        ANNOTATED_FILENAME_PATTERN,
    )
    owns_asset = await run_in_threadpool(
        analysis_draft_asset_belongs_to_user,
        user["id"],
        path,
    )
    if not owns_asset:
        raise HTTPException(status_code=404, detail="Image not found.")
    return FileResponse(path, media_type="image/jpeg", headers=TEMP_MEDIA_HEADERS)


async def _save_upload(image: UploadFile, destination: Path) -> None:
    await save_image_upload(
        image,
        destination,
        max_size=MAX_UPLOAD_SIZE,
        chunk_size=UPLOAD_CHUNK_SIZE,
    )


@router.post("/analyze", response_model=None)
async def analyze_uploaded_waste(
    user: Annotated[AuthenticatedUser, Depends(enforce_ai_analysis_rate_limit)],
    image: UploadFile = File(...),
) -> dict[str, Any] | JSONResponse:
    request_id = uuid4().hex[:12]
    request_started = perf_counter()
    logger.info("analysis_request_started request_id=%s", request_id)

    try:
        extension = validate_image_upload_metadata(image.filename, image.content_type)
    except UploadMetadataError as exc:
        await image.close()
        _log_analysis_failure(request_id, str(exc), request_started)
        return JSONResponse(
            status_code=415,
            content={
                "success": False,
                "code": str(exc),
                "message": (
                    "The image filename, extension, or MIME type is not supported. "
                    "Use a JPG, PNG, or WEBP image."
                ),
                "stage": "detection",
            },
        )

    try:
        destination = create_unique_upload_path(
            UPLOAD_DIR,
            prefix="upload",
            extension=extension,
        )
    except (OSError, ValueError):
        await image.close()
        _log_analysis_failure(
            request_id,
            "UPLOAD_STORAGE_ERROR",
            request_started,
            level=logging.ERROR,
        )
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "code": "UPLOAD_STORAGE_ERROR",
                "message": "The image could not be stored for analysis.",
                "stage": "detection",
            },
        )
    try:
        await _save_upload(image, destination)
    except ValueError as exc:
        code = str(exc)
        _log_analysis_failure(request_id, code, request_started)
        if code == "IMAGE_TOO_LARGE":
            return JSONResponse(
                status_code=413,
                content={
                    "success": False,
                    "code": code,
                    "message": upload_size_limit_message(MAX_UPLOAD_SIZE),
                    "stage": "detection",
                },
            )
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "code": "INVALID_IMAGE",
                "message": "The uploaded image is empty or invalid.",
                "stage": "detection",
            },
        )
    except OSError as exc:
        logger.exception(
            "analysis_upload_failed request_id=%s error_type=%s",
            request_id,
            type(exc).__name__,
        )
        _log_analysis_failure(
            request_id,
            "UPLOAD_STORAGE_ERROR",
            request_started,
            level=logging.ERROR,
        )
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "code": "UPLOAD_STORAGE_ERROR",
                "message": "The image could not be stored for analysis.",
                "stage": "detection",
            },
        )

    try:
        await run_in_threadpool(validate_image, destination)
    except ImageValidationError as exc:
        _remove_temporary_file(destination, UPLOAD_DIR)
        _log_analysis_failure(request_id, exc.code, request_started)
        return JSONResponse(
            status_code=_failure_status(exc.code),
            content={
                "success": False,
                "code": exc.code,
                "message": exc.public_message,
                "stage": "detection",
            },
        )
    logger.info(
        "analysis_image_validation_completed request_id=%s status=valid "
        "size_bytes=%d",
        request_id,
        destination.stat().st_size,
    )

    try:
        result = await run_in_threadpool(analyze_waste_image, destination)
    except Exception as exc:
        _remove_temporary_file(destination, UPLOAD_DIR)
        logger.exception(
            "analysis_pipeline_error request_id=%s error_type=%s",
            request_id,
            type(exc).__name__,
        )
        _log_analysis_failure(
            request_id,
            "ANALYSIS_ERROR",
            request_started,
            level=logging.ERROR,
        )
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "code": "ANALYSIS_ERROR",
                "message": "Waste analysis failed unexpectedly.",
                "stage": "detection",
            },
        )
    if result["success"] is not True:
        _remove_temporary_file(destination, UPLOAD_DIR)
        annotated_path = result.get("annotated_image")
        if isinstance(annotated_path, str):
            _remove_temporary_file(annotated_path, ANNOTATED_OUTPUT_DIR)
        _log_analysis_failure(request_id, result["code"], request_started)
        return JSONResponse(
            status_code=_failure_status(result["code"]),
            content=result,
        )

    try:
        annotated_image = _annotated_image_url(result["annotated_image"])
    except ValueError:
        _remove_temporary_file(destination, UPLOAD_DIR)
        _remove_temporary_file(result["annotated_image"], ANNOTATED_OUTPUT_DIR)
        _log_analysis_failure(
            request_id,
            "ANNOTATED_IMAGE_ERROR",
            request_started,
            level=logging.ERROR,
        )
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "code": "ANNOTATED_IMAGE_ERROR",
                "message": "The annotated image is unavailable.",
                "stage": "detection",
            },
        )

    try:
        analysis_id = await run_in_threadpool(
            create_analysis_draft,
            original_image_path=destination,
            annotated_image_path=result["annotated_image"],
            detection=result["detection"],
            report=result["report"],
            user_id=user["id"],
        )
    except (OSError, TypeError, ValueError, sqlite3.Error) as exc:
        _remove_temporary_file(destination, UPLOAD_DIR)
        _remove_temporary_file(result["annotated_image"], ANNOTATED_OUTPUT_DIR)
        logger.exception(
            "analysis_draft_storage_failed request_id=%s error_type=%s",
            request_id,
            type(exc).__name__,
        )
        _log_analysis_failure(
            request_id,
            "DRAFT_STORAGE_ERROR",
            request_started,
            level=logging.ERROR,
        )
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "code": "DRAFT_STORAGE_ERROR",
                "message": "The analysis draft could not be stored.",
                "stage": "report_generation",
            },
        )

    detection_count = result["detection"]["total_objects"]
    logger.info(
        "analysis_request_completed request_id=%s detection_count=%d "
        "duration_ms=%d",
        request_id,
        detection_count,
        round((perf_counter() - request_started) * 1000),
    )
    return {
        **result,
        "analysis_id": analysis_id,
        "original_image": f"/api/waste/uploads/{quote(destination.name)}",
        "annotated_image": annotated_image,
    }


__all__ = ["router"]
