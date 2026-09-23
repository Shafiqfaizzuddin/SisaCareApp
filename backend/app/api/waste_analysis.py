"""HTTP boundary for temporary waste-image analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, File, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.services.ai import analyze_waste_image
from app.services.ai.image_annotator import ANNOTATED_OUTPUT_DIR


router = APIRouter()

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "storage" / "tmp" / "uploads"
MAX_UPLOAD_SIZE = 10 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 1024 * 1024
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


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
        raise ValueError("Annotated image was created outside the output directory.") from exc

    return f"/api/waste/annotated/{quote(relative_path.as_posix())}"


async def _save_upload(image: UploadFile, destination: Path) -> None:
    total_size = 0
    try:
        with destination.open("wb") as output:
            while chunk := await image.read(UPLOAD_CHUNK_SIZE):
                total_size += len(chunk)
                if total_size > MAX_UPLOAD_SIZE:
                    raise ValueError("IMAGE_TOO_LARGE")
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await image.close()

    if total_size == 0:
        destination.unlink(missing_ok=True)
        raise ValueError("EMPTY_IMAGE")


@router.post("/analyze", response_model=None)
async def analyze_uploaded_waste(
    image: UploadFile = File(...),
) -> dict[str, Any] | JSONResponse:
    extension = ALLOWED_IMAGE_TYPES.get(image.content_type or "")
    if extension is None:
        await image.close()
        return JSONResponse(
            status_code=415,
            content={
                "success": False,
                "code": "UNSUPPORTED_FILE_TYPE",
                "message": "Unsupported file type. Use JPEG, PNG, or WEBP.",
                "stage": "detection",
            },
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destination = UPLOAD_DIR / f"upload-{uuid4().hex}{extension}"
    try:
        await _save_upload(image, destination)
    except ValueError as exc:
        code = str(exc)
        if code == "IMAGE_TOO_LARGE":
            return JSONResponse(
                status_code=413,
                content={
                    "success": False,
                    "code": code,
                    "message": "The image must be 10 MB or smaller.",
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
    except OSError:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "code": "UPLOAD_STORAGE_ERROR",
                "message": "The image could not be stored for analysis.",
                "stage": "detection",
            },
        )

    result = await run_in_threadpool(analyze_waste_image, destination)
    if result["success"] is not True:
        return JSONResponse(
            status_code=_failure_status(result["code"]),
            content=result,
        )

    try:
        annotated_image = _annotated_image_url(result["annotated_image"])
    except ValueError:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "code": "ANNOTATED_IMAGE_ERROR",
                "message": "The annotated image is unavailable.",
                "stage": "detection",
            },
        )

    return {
        **result,
        "original_image": f"/api/waste/uploads/{quote(destination.name)}",
        "annotated_image": annotated_image,
    }


__all__ = ["router"]
