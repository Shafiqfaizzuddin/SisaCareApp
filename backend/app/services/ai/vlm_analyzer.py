"""Ollama-backed vision service for structured waste image understanding."""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from time import perf_counter
from typing import Any, Literal, TypedDict, cast

import httpx

from app.core.config import get_settings
from app.services.ai.image_validation import ImageValidationError, validate_image


logger = logging.getLogger(__name__)

WasteCategory = Literal[
    "Non-Recyclable",
    "Recyclable Waste",
    "Bulky Waste",
    "Unknown",
]
ConfidenceLevel = Literal["high", "medium", "low"]

ALLOWED_CATEGORIES = {
    "Non-Recyclable",
    "Recyclable Waste",
    "Bulky Waste",
    "Unknown",
}
ALLOWED_CONFIDENCE_LEVELS = {"high", "medium", "low"}
VAGUE_OBJECT_NAMES = {"waste", "trash", "object", "material"}

VLM_OBJECT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "display_name": {"type": "string", "minLength": 1},
        "suggested_category": {
            "type": "string",
            "enum": sorted(ALLOWED_CATEGORIES),
        },
        "confidence_level": {
            "type": "string",
            "enum": sorted(ALLOWED_CONFIDENCE_LEVELS),
        },
        "reason": {"type": "string", "minLength": 1},
    },
    "required": [
        "name",
        "display_name",
        "suggested_category",
        "confidence_level",
        "reason",
    ],
    "additionalProperties": False,
}

VLM_RESPONSE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "scene_description": {"type": "string", "minLength": 1},
        "objects": {
            "type": "array",
            "items": VLM_OBJECT_JSON_SCHEMA,
        },
    },
    "required": ["scene_description", "objects"],
    "additionalProperties": False,
}

VLM_PROMPT = """Analyze the supplied image for visibly present waste objects.
Return JSON only and follow the supplied JSON schema exactly.

Rules:
1. Identify only waste objects that are visibly present in the image.
2. Do not invent or infer hidden objects.
3. Prefer concrete names such as plastic bottle, drink can, cardboard box,
   food wrapper, mattress, or refrigerator.
4. Do not use vague object names such as waste, trash, object, or material.
5. suggested_category must be exactly one of: Non-Recyclable,
   Recyclable Waste, Bulky Waste, or Unknown.
6. Use Unknown when the visible evidence is insufficient for a category.
7. Set confidence_level to high, medium, or low based only on visible evidence.
8. Keep reason short and explain the visible evidence for the object name and
   suggested category.
9. Do not estimate weight, volume, dimensions, location, ownership, hazards,
   or events outside the image.
10. Do not invent an exact count. You may describe multiple items only when
    the individual items are visually clear.
11. Do not write a user-facing waste report or cleanup recommendation.
12. If no waste object is visibly identifiable, return an empty objects array
    and describe only what is visibly clear in scene_description.
"""


class VlmObject(TypedDict):
    name: str
    display_name: str
    suggested_category: WasteCategory
    confidence_level: ConfidenceLevel
    reason: str


class VlmAnalysis(TypedDict):
    scene_description: str
    objects: list[VlmObject]


VlmErrorCode = Literal[
    "IMAGE_NOT_FOUND",
    "INVALID_IMAGE",
    "UNSUPPORTED_FILE_TYPE",
    "OLLAMA_VISION_MODEL_NOT_CONFIGURED",
    "OLLAMA_UNAVAILABLE",
    "OLLAMA_VISION_MODEL_NOT_INSTALLED",
    "OLLAMA_TIMEOUT",
    "OLLAMA_API_ERROR",
    "INVALID_VLM_JSON",
    "MALFORMED_VLM_OUTPUT",
    "VLM_ANALYSIS_ERROR",
]


class VlmAnalysisFailure(TypedDict):
    success: Literal[False]
    code: VlmErrorCode
    message: str


VlmAnalysisResponse = VlmAnalysis | VlmAnalysisFailure


class InvalidVlmJsonError(ValueError):
    """Raised when Ollama or the generated model content is not valid JSON."""


class MalformedVlmOutputError(ValueError):
    """Raised when generated JSON does not match the required output contract."""


def _failure(code: VlmErrorCode, message: str) -> VlmAnalysisFailure:
    return {"success": False, "code": code, "message": message}


def _non_empty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MalformedVlmOutputError(f"{field} must be a non-empty string.")
    return value.strip()


def _validate_generated_output(value: object) -> VlmAnalysis:
    if not isinstance(value, dict) or set(value) != {"scene_description", "objects"}:
        raise MalformedVlmOutputError(
            "VLM output must contain only scene_description and objects."
        )

    scene_description = _non_empty_string(
        value.get("scene_description"),
        "scene_description",
    )
    raw_objects = value.get("objects")
    if not isinstance(raw_objects, list):
        raise MalformedVlmOutputError("objects must be an array.")

    objects: list[VlmObject] = []
    required_fields = {
        "name",
        "display_name",
        "suggested_category",
        "confidence_level",
        "reason",
    }
    for index, raw_object in enumerate(raw_objects):
        if not isinstance(raw_object, dict) or set(raw_object) != required_fields:
            raise MalformedVlmOutputError(
                f"objects[{index}] does not match the required object structure."
            )

        name = _non_empty_string(raw_object.get("name"), f"objects[{index}].name")
        display_name = _non_empty_string(
            raw_object.get("display_name"),
            f"objects[{index}].display_name",
        )
        reason = _non_empty_string(
            raw_object.get("reason"),
            f"objects[{index}].reason",
        )
        if name.casefold() in VAGUE_OBJECT_NAMES:
            raise MalformedVlmOutputError(
                f"objects[{index}].name must be a concrete waste object name."
            )

        category = raw_object.get("suggested_category")
        if category not in ALLOWED_CATEGORIES:
            raise MalformedVlmOutputError(
                f"objects[{index}].suggested_category is not allowed."
            )
        confidence = raw_object.get("confidence_level")
        if confidence not in ALLOWED_CONFIDENCE_LEVELS:
            raise MalformedVlmOutputError(
                f"objects[{index}].confidence_level is not allowed."
            )

        objects.append(
            {
                "name": name,
                "display_name": display_name,
                "suggested_category": cast(WasteCategory, category),
                "confidence_level": cast(ConfidenceLevel, confidence),
                "reason": reason,
            }
        )

    return {"scene_description": scene_description, "objects": objects}


def _parse_ollama_response(response: httpx.Response) -> VlmAnalysis:
    try:
        response_data: Any = response.json()
    except ValueError as exc:
        raise InvalidVlmJsonError("Ollama returned an unreadable JSON response.") from exc

    if not isinstance(response_data, dict) or response_data.get("done") is not True:
        raise MalformedVlmOutputError("Ollama response is incomplete or malformed.")
    generated_text = response_data.get("response")
    if not isinstance(generated_text, str) or not generated_text.strip():
        raise MalformedVlmOutputError("Ollama response contains no generated JSON.")

    try:
        generated_output: Any = json.loads(generated_text)
    except json.JSONDecodeError as exc:
        raise InvalidVlmJsonError("The vision model generated invalid JSON.") from exc
    return _validate_generated_output(generated_output)


def analyze_waste_image_with_vlm(
    image_path: str | Path,
    *,
    base_url: str | None = None,
    model: str | None = None,
    timeout_seconds: float | None = None,
    client: httpx.Client | None = None,
) -> VlmAnalysisResponse:
    """Analyze one validated image with Ollama and return structured visual facts."""

    try:
        resolved_image_path = validate_image(image_path)
    except ImageValidationError as exc:
        return _failure(exc.code, exc.public_message)  # type: ignore[arg-type]

    settings = get_settings()
    configured_base_url = base_url or settings.ollama_base_url
    configured_model = (
        model if model is not None else settings.ollama_vision_model
    ).strip()
    configured_timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else settings.ollama_vision_timeout_seconds
    )
    if not configured_model:
        logger.error("vlm_analysis_failed code=OLLAMA_VISION_MODEL_NOT_CONFIGURED")
        return _failure(
            "OLLAMA_VISION_MODEL_NOT_CONFIGURED",
            "The Ollama vision model is not configured.",
        )

    try:
        encoded_image = base64.b64encode(resolved_image_path.read_bytes()).decode("ascii")
    except OSError as exc:
        logger.error(
            "vlm_analysis_failed code=VLM_ANALYSIS_ERROR error_type=%s",
            type(exc).__name__,
        )
        return _failure(
            "VLM_ANALYSIS_ERROR",
            "The image could not be prepared for vision analysis.",
        )

    payload = {
        "model": configured_model,
        "prompt": VLM_PROMPT,
        "images": [encoded_image],
        "stream": False,
        "format": VLM_RESPONSE_JSON_SCHEMA,
        "options": {"temperature": 0},
        "keep_alive": settings.ollama_keep_alive,
    }
    owns_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(
            configured_timeout,
            connect=min(5.0, configured_timeout),
        )
    )
    request_started = perf_counter()
    logger.info("vlm_analysis_started")

    try:
        try:
            response = active_client.post(
                f"{configured_base_url.rstrip('/')}/api/generate",
                json=payload,
            )
        except httpx.TimeoutException:
            logger.warning(
                "vlm_analysis_failed code=OLLAMA_TIMEOUT duration_ms=%d",
                round((perf_counter() - request_started) * 1000),
            )
            return _failure(
                "OLLAMA_TIMEOUT",
                "Ollama did not respond before the vision analysis timeout.",
            )
        except httpx.RequestError:
            logger.error(
                "vlm_analysis_failed code=OLLAMA_UNAVAILABLE duration_ms=%d",
                round((perf_counter() - request_started) * 1000),
            )
            return _failure(
                "OLLAMA_UNAVAILABLE",
                "The Ollama vision service is unavailable.",
            )

        if response.status_code == 404:
            logger.error(
                "vlm_analysis_failed code=OLLAMA_VISION_MODEL_NOT_INSTALLED "
                "http_status=%d duration_ms=%d",
                response.status_code,
                round((perf_counter() - request_started) * 1000),
            )
            return _failure(
                "OLLAMA_VISION_MODEL_NOT_INSTALLED",
                "The configured Ollama vision model is unavailable.",
            )
        if response.is_error:
            logger.error(
                "vlm_analysis_failed code=OLLAMA_API_ERROR http_status=%d duration_ms=%d",
                response.status_code,
                round((perf_counter() - request_started) * 1000),
            )
            return _failure(
                "OLLAMA_API_ERROR",
                "The Ollama vision service returned an error.",
            )

        try:
            result = _parse_ollama_response(response)
        except InvalidVlmJsonError:
            logger.warning(
                "vlm_analysis_failed code=INVALID_VLM_JSON duration_ms=%d",
                round((perf_counter() - request_started) * 1000),
            )
            return _failure(
                "INVALID_VLM_JSON",
                "The vision model returned invalid JSON.",
            )
        except MalformedVlmOutputError:
            logger.warning(
                "vlm_analysis_failed code=MALFORMED_VLM_OUTPUT duration_ms=%d",
                round((perf_counter() - request_started) * 1000),
            )
            return _failure(
                "MALFORMED_VLM_OUTPUT",
                "The vision model output does not match the required structure.",
            )

        logger.info(
            "vlm_analysis_completed object_count=%d duration_ms=%d",
            len(result["objects"]),
            round((perf_counter() - request_started) * 1000),
        )
        return result
    except Exception as exc:
        logger.error(
            "vlm_analysis_failed code=VLM_ANALYSIS_ERROR error_type=%s",
            type(exc).__name__,
        )
        return _failure(
            "VLM_ANALYSIS_ERROR",
            "Vision analysis failed unexpectedly.",
        )
    finally:
        if owns_client:
            active_client.close()


__all__ = [
    "ALLOWED_CATEGORIES",
    "ALLOWED_CONFIDENCE_LEVELS",
    "ConfidenceLevel",
    "VLM_PROMPT",
    "VLM_RESPONSE_JSON_SCHEMA",
    "VlmAnalysis",
    "VlmAnalysisFailure",
    "VlmAnalysisResponse",
    "VlmObject",
    "WasteCategory",
    "analyze_waste_image_with_vlm",
]
