"""Coordinate validated YOLO and VLM analysis with independent fallbacks."""

from __future__ import annotations

import logging
from pathlib import Path
from time import perf_counter
from typing import Literal, TypedDict, cast

from app.services.ai.category_mapping import WasteCategory
from app.services.ai.fusion_service import FusedWasteObject, fuse_waste_objects
from app.services.ai.grouping_service import GroupedWasteObject, group_fused_objects
from app.services.ai.image_validation import ImageValidationError, validate_image
from app.services.ai.vlm_analyzer import (
    VlmAnalysis,
    VlmObject,
    analyze_waste_image_with_vlm,
)
from app.services.ai.yolo_detector import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    WasteDetection,
    WasteDetectionResult,
    detect_waste,
)


logger = logging.getLogger(__name__)
CATEGORY_ORDER: tuple[WasteCategory, ...] = (
    "Non-Recyclable",
    "Recyclable Waste",
    "Bulky Waste",
    "Unknown",
)


class AnalysisServiceError(TypedDict):
    code: str
    message: str


class YoloAnalysis(TypedDict):
    available: bool
    total_objects: int
    counts: dict[str, int]
    detections: list[WasteDetection]
    error: AnalysisServiceError | None


class VlmAnalysisSummary(TypedDict):
    available: bool
    scene_description: str | None
    objects: list[VlmObject]
    error: AnalysisServiceError | None


AnalysisMode = Literal["hybrid", "yolo_only", "vlm_only", "unavailable"]


class HybridAnalysis(TypedDict):
    mode: AnalysisMode
    objects: list[FusedWasteObject]
    grouped_objects: list[GroupedWasteObject]
    categories_detected: list[WasteCategory]


class WasteAnalysisResult(TypedDict):
    success: Literal[True]
    original_image: str
    yolo: YoloAnalysis
    vlm: VlmAnalysisSummary
    analysis: HybridAnalysis
    annotated_image: str | None


class WasteAnalysisFailure(TypedDict):
    success: Literal[False]
    code: str
    message: str
    stage: Literal["validation", "analysis"]
    yolo: YoloAnalysis
    vlm: VlmAnalysisSummary
    analysis: HybridAnalysis
    annotated_image: str | None


WasteAnalysisResponse = WasteAnalysisResult | WasteAnalysisFailure


def _service_error(code: str, message: str) -> AnalysisServiceError:
    return {"code": code, "message": message}


def _unavailable_yolo(code: str, message: str) -> YoloAnalysis:
    return {
        "available": False,
        "total_objects": 0,
        "counts": {},
        "detections": [],
        "error": _service_error(code, message),
    }


def _unavailable_vlm(code: str, message: str) -> VlmAnalysisSummary:
    return {
        "available": False,
        "scene_description": None,
        "objects": [],
        "error": _service_error(code, message),
    }


def _empty_analysis(mode: AnalysisMode = "unavailable") -> HybridAnalysis:
    return {
        "mode": mode,
        "objects": [],
        "grouped_objects": [],
        "categories_detected": [],
    }


def _failure(
    code: str,
    message: str,
    stage: Literal["validation", "analysis"],
    *,
    yolo: YoloAnalysis,
    vlm: VlmAnalysisSummary,
    analysis: HybridAnalysis | None = None,
    annotated_image: str | None = None,
) -> WasteAnalysisFailure:
    return {
        "success": False,
        "code": code,
        "message": message,
        "stage": stage,
        "yolo": yolo,
        "vlm": vlm,
        "analysis": analysis or _empty_analysis(),
        "annotated_image": annotated_image,
    }


def _run_yolo(
    image_path: Path,
    confidence_threshold: float,
) -> tuple[YoloAnalysis, str | None]:
    started_at = perf_counter()
    try:
        response = detect_waste(image_path, confidence_threshold)
    except Exception as exc:
        logger.exception(
            "hybrid_yolo_failed code=YOLO_ANALYSIS_ERROR error_type=%s",
            type(exc).__name__,
        )
        result = _unavailable_yolo(
            "YOLO_ANALYSIS_ERROR",
            "YOLO waste detection failed unexpectedly.",
        )
        annotated_image = None
    else:
        if response["success"] is True:
            detection = cast(WasteDetectionResult, response)
            result = {
                "available": True,
                "total_objects": detection["total_objects"],
                "counts": detection["counts"],
                "detections": detection["detections"],
                "error": None,
            }
            annotated_image = detection["annotated_image_path"]
        else:
            result = _unavailable_yolo(response["code"], response["message"])
            annotated_image = None
    logger.info(
        "hybrid_yolo_completed duration_ms=%d available=%s object_count=%d",
        round((perf_counter() - started_at) * 1000),
        result["available"],
        result["total_objects"],
    )
    return result, annotated_image


def _run_vlm(image_path: Path) -> VlmAnalysisSummary:
    started_at = perf_counter()
    try:
        response = analyze_waste_image_with_vlm(image_path)
    except Exception as exc:
        logger.exception(
            "hybrid_vlm_failed code=VLM_ANALYSIS_ERROR error_type=%s",
            type(exc).__name__,
        )
        result = _unavailable_vlm(
            "VLM_ANALYSIS_ERROR",
            "Vision-language waste analysis failed unexpectedly.",
        )
    else:
        if response.get("success") is False:
            result = _unavailable_vlm(response["code"], response["message"])
        else:
            analysis = cast(VlmAnalysis, response)
            result = {
                "available": True,
                "scene_description": analysis["scene_description"],
                "objects": analysis["objects"],
                "error": None,
            }
    logger.info(
        "hybrid_vlm_completed duration_ms=%d available=%s object_count=%d",
        round((perf_counter() - started_at) * 1000),
        result["available"],
        len(result["objects"]),
    )
    return result


def _analysis_mode(yolo_available: bool, vlm_available: bool) -> AnalysisMode:
    if yolo_available and vlm_available:
        return "hybrid"
    if yolo_available:
        return "yolo_only"
    if vlm_available:
        return "vlm_only"
    return "unavailable"


def _categories_detected(objects: list[FusedWasteObject]) -> list[WasteCategory]:
    present = {item["category"] for item in objects}
    return [category for category in CATEGORY_ORDER if category in present]


def analyze_waste_image(
    image_path: str | Path,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> WasteAnalysisResponse:
    """Run the complete hybrid analysis without generating a user report."""

    total_started_at = perf_counter()
    try:
        resolved_image_path = validate_image(image_path)
    except ImageValidationError as exc:
        logger.warning("hybrid_analysis_validation_failed code=%s", exc.code)
        yolo = _unavailable_yolo(exc.code, exc.public_message)
        vlm = _unavailable_vlm(exc.code, exc.public_message)
        return _failure(
            exc.code,
            exc.public_message,
            "validation",
            yolo=yolo,
            vlm=vlm,
        )
    except Exception as exc:
        logger.exception(
            "hybrid_analysis_validation_failed code=INVALID_IMAGE error_type=%s",
            type(exc).__name__,
        )
        message = "The supplied image could not be validated."
        yolo = _unavailable_yolo("INVALID_IMAGE", message)
        vlm = _unavailable_vlm("INVALID_IMAGE", message)
        return _failure(
            "INVALID_IMAGE",
            message,
            "validation",
            yolo=yolo,
            vlm=vlm,
        )

    yolo, annotated_image = _run_yolo(
        resolved_image_path,
        confidence_threshold,
    )
    vlm = _run_vlm(resolved_image_path)
    mode = _analysis_mode(yolo["available"], vlm["available"])

    if mode == "unavailable":
        logger.error(
            "hybrid_analysis_failed code=AI_ANALYSIS_FAILED total_duration_ms=%d",
            round((perf_counter() - total_started_at) * 1000),
        )
        return _failure(
            "AI_ANALYSIS_FAILED",
            "Waste analysis is temporarily unavailable. Please try again.",
            "analysis",
            yolo=yolo,
            vlm=vlm,
        )

    fusion_started_at = perf_counter()
    try:
        fused_objects = fuse_waste_objects(
            yolo["detections"] if yolo["available"] else [],
            vlm["objects"] if vlm["available"] else [],
        )
        grouped_objects = group_fused_objects(fused_objects)["grouped_objects"]
    except Exception as exc:
        logger.exception(
            "hybrid_fusion_failed code=FUSION_ERROR error_type=%s",
            type(exc).__name__,
        )
        return _failure(
            "AI_ANALYSIS_FAILED",
            "Waste analysis results could not be combined safely.",
            "analysis",
            yolo=yolo,
            vlm=vlm,
            annotated_image=annotated_image,
        )
    fusion_ms = round((perf_counter() - fusion_started_at) * 1000)
    logger.info(
        "hybrid_fusion_completed duration_ms=%d object_count=%d group_count=%d",
        fusion_ms,
        len(fused_objects),
        len(grouped_objects),
    )

    analysis: HybridAnalysis = {
        "mode": mode,
        "objects": fused_objects,
        "grouped_objects": grouped_objects,
        "categories_detected": _categories_detected(fused_objects),
    }
    total_ms = round((perf_counter() - total_started_at) * 1000)
    if not fused_objects:
        logger.info(
            "hybrid_analysis_completed code=NO_WASTE_DETECTED mode=%s "
            "total_duration_ms=%d",
            mode,
            total_ms,
        )
        return _failure(
            "NO_WASTE_DETECTED",
            "No recognizable waste objects were found in the image.",
            "analysis",
            yolo=yolo,
            vlm=vlm,
            analysis=analysis,
            annotated_image=annotated_image,
        )

    logger.info(
        "hybrid_analysis_completed code=ANALYSIS_COMPLETE mode=%s "
        "total_duration_ms=%d",
        mode,
        total_ms,
    )
    return {
        "success": True,
        "original_image": str(resolved_image_path),
        "yolo": yolo,
        "vlm": vlm,
        "analysis": analysis,
        "annotated_image": annotated_image,
    }


__all__ = [
    "AnalysisMode",
    "AnalysisServiceError",
    "HybridAnalysis",
    "VlmAnalysisSummary",
    "WasteAnalysisFailure",
    "WasteAnalysisResponse",
    "WasteAnalysisResult",
    "YoloAnalysis",
    "analyze_waste_image",
]
