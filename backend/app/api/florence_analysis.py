"""Active location-free photo analysis through the local Florence-2 service."""

from __future__ import annotations

import logging
import math
import sqlite3
import asyncio
from pathlib import Path
from time import perf_counter
from typing import Annotated, Any
from urllib.parse import quote
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from PIL import Image, ImageOps
from pydantic import BaseModel, Field

from app.core.auth import AuthenticatedUser, require_authenticated_user
from app.core.config import get_settings
from app.core.rate_limit import enforce_ai_analysis_rate_limit
from app.repositories.reports import create_analysis_draft
from app.services.ai.image_validation import ImageValidationError, validate_image
from app.services.ai.waste_rules import classify_item
from app.services.ai.visual_fallback import VisualFallbackError, resolve_detection, resolve_batch
from app.services.ai.grouping_service import group_report_observations
from app.services.image_uploads import (
    MAX_UPLOAD_SIZE,
    UploadMetadataError,
    create_unique_upload_path,
    save_image_upload,
    validate_image_upload_metadata,
)


log = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()
UPLOAD_DIR = settings.upload_dir
PREVIEW_DIR = settings.annotated_output_dir
_visual_limit = asyncio.Semaphore(1)

# These objects are shown to the user and persisted, including when marked as
# background. The set only suggests a review state; it never removes a result.
BACKGROUND_LABELS = frozenset({
    "person", "people", "car", "vehicle", "land_vehicle", "wheel", "door_handle", "road",
    "street", "tree", "sky", "building", "wall", "grass", "ground",
    "window", "door", "floor", "cloud", "sign", "shadow",
})


class ConfirmedItemRuleRequest(BaseModel):
    label: str = Field(min_length=1, max_length=150)
    material: str = Field(default="Unknown", max_length=150)
    condition_answers: dict[str, bool] = Field(default_factory=dict)


@router.post("/classify")
async def classify_confirmed_item(
    request: ConfirmedItemRuleRequest,
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> dict[str, Any]:
    if user["role"] != "user":
        raise HTTPException(status_code=403, detail="Participant access is required.")
    return classify_item(
        request.label, confirmed_material=request.material if request.material != "Unknown" else None,
        answers=request.condition_answers, user_confirmed=True,
    )


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={
        "success": False, "code": code, "message": message,
    })


def _oriented_preview(source_path: Path, destination_path: Path) -> tuple[int, int]:
    with Image.open(source_path) as source:
        oriented = ImageOps.exif_transpose(source)
        rgb = oriented.convert("RGB")
        dimensions = rgb.size
        rgb.save(destination_path, format="JPEG", quality=92)
    return dimensions


def _validate_service_result(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("success") is not True:
        raise ValueError("Florence response is not a successful detection result.")
    width, height = value.get("image_width"), value.get("image_height")
    if (not isinstance(width, int) or isinstance(width, bool) or width < 1
            or not isinstance(height, int) or isinstance(height, bool) or height < 1):
        raise ValueError("Florence response has invalid image dimensions.")
    if value.get("model_id") not in {"microsoft/Florence-2-base", "microsoft/Florence-2-large"}:
        raise ValueError("Florence response has an unexpected model identifier.")
    if not isinstance(value.get("model_revision"), str) or not isinstance(value.get("analysis_id"), str):
        raise ValueError("Florence response is missing model metadata.")
    raw = value.get("detections")
    if not isinstance(raw, list):
        raise ValueError("Florence response is missing detections.")
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("label"), str) or not item["label"].strip():
            raise ValueError("Florence response contains an invalid label.")
        box = item.get("bounding_box")
        if not isinstance(box, dict) or set(box) != {"x1", "y1", "x2", "y2"}:
            raise ValueError("Florence response contains an invalid box.")
        try:
            x1, y1, x2, y2 = (float(box[key]) for key in ("x1", "y1", "x2", "y2"))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Florence response contains an invalid coordinate.") from exc
        if not all(math.isfinite(value) for value in (x1, y1, x2, y2)) or not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            raise ValueError("Florence response contains an out-of-bounds box.")
    return value


def _review_detection(item: dict[str, Any], index: int) -> dict[str, Any]:
    result = classify_item(item["label"])
    name = result["canonical_item"]
    status = (
        "background" if name in BACKGROUND_LABELS else
        "likely_waste" if result["category"] is not None else
        "needs_confirmation"
    )
    return {
        "id": f"det-{index}",
        "label": item["label"],
        "original_label": result["original_label"],
        "name": name,
        "canonical_name": result["canonical_name"],
        "display_name": result["display_name"],
        "bounding_box": item["bounding_box"],
        "confidence": None,
        "review_status": status,
        "suggested_category": result["category"],
        "waste_category": result["waste_category"],
        "needs_confirmation": result["needs_confirmation"],
        "confirmation_question": result["confirmation_question"],
        "material": result["material"] or "Unknown",
        "recommended_handling": result["handling_guidance"],
        "confirmation_reason": result["confirmation_reason"],
        "questions": result["questions"],
        "station_material_key": result["station_material_key"],
        "rule_id": result["rule_id"],
        "classification_source": result["classification_source"],
        "bulky": result["bulky"],
        "visual_assessment": None,
    }


def _apply_visual_result(item: dict[str, Any], visual: dict[str, Any]) -> None:
    item["visual_assessment"] = visual
    item["classification_source"] = "vision"
    if visual["decision"] == "background":
        item["review_status"] = "background"
        item["confirmation_reason"] = visual["visual_justification"]
        return
    rule = classify_item(visual["object_name"], confirmed_material=visual["material"] if visual["material"].casefold() != "unknown" else None)
    item["name"] = rule["canonical_name"]
    item["canonical_name"] = rule["canonical_name"]
    item["display_name"] = rule["display_name"]
    item["material"] = rule["material"] or (visual["material"] if visual["material"].casefold() != "unknown" else "Unknown")
    item["suggested_category"] = rule["category"] or visual["category"]
    item["waste_category"] = item["suggested_category"]
    item["review_status"] = "likely_waste"
    item["needs_confirmation"] = visual["uncertain"]
    item["confirmation_reason"] = visual["visual_justification"] if visual["uncertain"] else None
    item["confirmation_question"] = None
    item["rule_id"] = rule["rule_id"]
    item["station_material_key"] = rule["station_material_key"] if rule["category"] == "Recyclable Waste" else None
    item["recommended_handling"] = rule["handling_guidance"] if rule["rule_id"] else "Ask the municipal review team to assess the item and appropriate handling."


async def _resolve_visual_candidates(preview_path: Path, detections: list[dict[str, Any]]) -> VisualFallbackError | None:
    candidates = [item for item in detections if item["review_status"] == "needs_confirmation"]
    if not candidates:
        return None
    if len(candidates) > 40:
        return VisualFallbackError("VISION_LIMIT", "Too many ambiguous detections for one local analysis. Try a clearer photo or smaller scene.")
    with Image.open(preview_path) as source:
        image = source.convert("RGB")
    for start in range(0, len(candidates), 4):
        batch = candidates[start:start + 4]
        async with _visual_limit:
            if len(batch) > 1:
                try:
                    resolved = await resolve_batch(image, batch)
                except VisualFallbackError as exc:
                    if exc.code not in {"VISION_UNAVAILABLE", "VISION_TIMEOUT", "VISION_INVALID_OUTPUT"}:
                        return exc
                    log.warning("visual_batch_retry_as_single code=%s", exc.code)
                else:
                    for item in batch:
                        _apply_visual_result(item, resolved[item["id"]])
                    continue
            for item in batch:
                try:
                    _apply_visual_result(item, await resolve_detection(image, item))
                except VisualFallbackError as exc:
                    return exc
    return None


@router.post("/analyze", response_model=None)
async def analyze_uploaded_waste(
    user: Annotated[AuthenticatedUser, Depends(enforce_ai_analysis_rate_limit)],
    image: UploadFile = File(...),
) -> dict[str, Any] | JSONResponse:
    started = perf_counter()
    try:
        extension = validate_image_upload_metadata(image.filename, image.content_type)
    except UploadMetadataError:
        await image.close()
        return _error(415, "UNSUPPORTED_IMAGE_TYPE", "Use a JPG, PNG, or WEBP image.")
    content_type = image.content_type or ""
    original_path = create_unique_upload_path(UPLOAD_DIR, prefix="upload", extension=extension)
    preview_path: Path | None = None
    completed = False
    try:
        try:
            await save_image_upload(image, original_path, max_size=MAX_UPLOAD_SIZE)
            await run_in_threadpool(validate_image, original_path)
        except ImageValidationError as exc:
            return _error(400, exc.code, exc.public_message)
        except ValueError as exc:
            if str(exc) == "IMAGE_TOO_LARGE":
                return _error(413, "IMAGE_TOO_LARGE", "Image exceeds the 10 MB upload limit.")
            return _error(400, "INVALID_IMAGE", "The uploaded image is empty or invalid.")

        try:
            async with httpx.AsyncClient(timeout=settings.florence_service_timeout_seconds) as client:
                with original_path.open("rb") as source:
                    response = await client.post(
                        f"{settings.florence_service_url.rstrip('/')}/detect",
                        files={"image": (original_path.name, source, content_type)},
                    )
        except httpx.TimeoutException:
            return _error(504, "FLORENCE_TIMEOUT", "Local photo analysis timed out. You can identify items manually.")
        except httpx.RequestError:
            return _error(503, "FLORENCE_UNAVAILABLE", "Local photo analysis is unavailable. You can identify items manually.")
        try:
            service_result = response.json()
        except ValueError:
            return _error(502, "FLORENCE_INVALID_RESPONSE", "Local photo analysis returned an invalid response.")
        if response.status_code != 200:
            code = service_result.get("error", {}).get("code") if isinstance(service_result, dict) and isinstance(service_result.get("error"), dict) else "FLORENCE_UNAVAILABLE"
            status = 504 if response.status_code == 504 else 503 if response.status_code in {429, 503} else 502
            return _error(status, str(code), "Local photo analysis could not complete. You can identify items manually.")
        try:
            result = _validate_service_result(service_result)
            raw_detections = [_review_detection(item, index) for index, item in enumerate(result["detections"])]
        except (ValueError, TypeError, KeyError) as exc:
            log.warning("florence_invalid_response error_type=%s", type(exc).__name__)
            return _error(502, "FLORENCE_INVALID_RESPONSE", "Local photo analysis returned an invalid response.")

        preview_path = create_unique_upload_path(PREVIEW_DIR, prefix="annotated", extension=".jpg")
        preview_dimensions = await run_in_threadpool(_oriented_preview, original_path, preview_path)
        if preview_dimensions != (result["image_width"], result["image_height"]):
            return _error(502, "FLORENCE_DIMENSION_MISMATCH", "Photo dimensions did not match local analysis.")

        visual_failure = await _resolve_visual_candidates(preview_path, raw_detections)
        groups = group_report_observations([{
            "name": item["name"], "material": item["material"],
            "category": item["suggested_category"], "source_detection_id": item["id"],
            "uncertainty_reason": item["confirmation_reason"] if item["needs_confirmation"] else None,
        } for item in raw_detections if item["review_status"] == "likely_waste"])

        draft_payload = {
            "provider": "florence2",
            "model_id": result["model_id"],
            "model_revision": result["model_revision"],
            "visual_model_id": settings.ollama_vision_model if any(item["visual_assessment"] is not None for item in raw_detections) else None,
            "service_analysis_id": result["analysis_id"],
            "image_width": result["image_width"],
            "image_height": result["image_height"],
            # Unmodified labels/boxes from the detector, apart from its own
            # documented clipping. Review suggestions are stored separately.
            "model_detections": result["detections"],
            "raw_detections": raw_detections,
            "grouped_waste": groups,
            "visual_failure": {"code": visual_failure.code, "message": str(visual_failure)} if visual_failure else None,
            "detections": [{
                "class_name": item["name"], "display_name": item["display_name"],
                "waste_category": item["suggested_category"] or "Needs Confirmation",
                "material": item["material"], "confidence": None,
                "bounding_box": item["bounding_box"], "source": "florence2",
                "review_status": item["review_status"],
            } for item in raw_detections],
            "analysis": {
                "mode": "florence2", "provider": "florence2",
                "model_id": result["model_id"],
                "model_revision": result["model_revision"],
                "visual_model_id": settings.ollama_vision_model if any(item["visual_assessment"] is not None for item in raw_detections) else None,
                "categories_detected": list(dict.fromkeys(
                    item["suggested_category"] for item in raw_detections
                    if item["suggested_category"] is not None
                )),
            },
        }
        analysis_id = await run_in_threadpool(
            create_analysis_draft,
            original_image_path=original_path,
            annotated_image_path=preview_path,
            detection=draft_payload,
            report=None,
            user_id=user["id"],
        )
        completed = True
        if visual_failure:
            return JSONResponse(status_code=503, content={
                "success": False, "code": visual_failure.code, "message": str(visual_failure),
                "analysis_id": analysis_id, "completed_detections": raw_detections,
            })
        log.info("florence_analysis_completed analysis_id=%s count=%d duration_ms=%d",
                 analysis_id, len(raw_detections), round((perf_counter() - started) * 1000))
        return {
            "success": True, "analysis_id": analysis_id,
            "original_image": f"/api/waste/uploads/{quote(original_path.name)}",
            "display_image": f"/api/waste/annotated/{quote(preview_path.name)}",
            "image_width": result["image_width"], "image_height": result["image_height"],
            "provider": "florence2", "model_id": result["model_id"],
            "model_revision": result["model_revision"],
            "detections": raw_detections,
            "groups": groups,
            "processing_time_ms": result["processing_time_ms"],
            "warnings": result.get("warnings", []),
        }
    except (OSError, sqlite3.Error, TypeError, ValueError):
        log.exception("florence_analysis_storage_failed")
        return _error(500, "ANALYSIS_STORAGE_ERROR", "The analysis draft could not be stored.")
    finally:
        if not completed:
            original_path.unlink(missing_ok=True)
            if preview_path is not None:
                preview_path.unlink(missing_ok=True)
