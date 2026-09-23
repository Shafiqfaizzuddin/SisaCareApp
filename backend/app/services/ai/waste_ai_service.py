"""Coordinate waste detection and report generation without duplicating them."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, NotRequired, TypedDict, cast

from app.services.ai.ollama_report_generator import (
    ReportGenerationFailure,
    WasteReport,
    generate_waste_report,
)
from app.services.ai.yolo_detector import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    WasteDetection,
    WasteDetectionResult,
    detect_waste,
)


class AnalysisDetection(TypedDict):
    total_objects: int
    counts: dict[str, int]
    detections: list[WasteDetection]


class WasteAnalysisResult(TypedDict):
    success: Literal[True]
    original_image: str
    annotated_image: str
    detection: AnalysisDetection
    report: WasteReport


class WasteAnalysisFailure(TypedDict):
    success: Literal[False]
    code: str
    message: str
    stage: Literal["detection", "report_generation"]
    original_image: NotRequired[str]
    annotated_image: NotRequired[str]
    detection: NotRequired[AnalysisDetection]


WasteAnalysisResponse = WasteAnalysisResult | WasteAnalysisFailure


def _detection_summary(result: WasteDetectionResult) -> AnalysisDetection:
    return {
        "total_objects": result["total_objects"],
        "counts": result["counts"],
        "detections": result["detections"],
    }


def _detection_failure(code: str, message: str) -> WasteAnalysisFailure:
    return {
        "success": False,
        "code": code,
        "message": message,
        "stage": "detection",
    }


def analyze_waste_image(
    image_path: str | Path,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> WasteAnalysisResponse:
    """Run the existing detector, then generate a report for its detections.

    Image validation, YOLO inference, annotation, category mapping, and counting
    remain owned by ``detect_waste``. This function only coordinates service
    results and never sends an image to Ollama.
    """
    try:
        detection_response = detect_waste(image_path, confidence_threshold)
    except Exception:
        return _detection_failure(
            "ANALYSIS_ERROR",
            "Waste image analysis failed unexpectedly during detection.",
        )

    if detection_response["success"] is not True:
        return _detection_failure(
            detection_response["code"],
            detection_response["message"],
        )

    detection_result = cast(WasteDetectionResult, detection_response)
    if (
        detection_result["total_objects"] <= 0
        or not detection_result["detections"]
    ):
        return _detection_failure(
            "NO_WASTE_DETECTED",
            "No supported waste objects were detected in this image.",
        )

    original_image = str(Path(image_path).expanduser().resolve())
    annotated_image = detection_result["annotated_image_path"]
    detection = _detection_summary(detection_result)

    try:
        report_response = generate_waste_report(detection_result)
    except Exception:
        return {
            "success": False,
            "code": "ANALYSIS_ERROR",
            "message": "Waste image analysis failed during report generation.",
            "stage": "report_generation",
            "original_image": original_image,
            "annotated_image": annotated_image,
            "detection": detection,
        }

    if report_response.get("success") is False:
        report_failure = cast(ReportGenerationFailure, report_response)
        return {
            "success": False,
            "code": report_failure["code"],
            "message": report_failure["message"],
            "stage": "report_generation",
            "original_image": original_image,
            "annotated_image": annotated_image,
            "detection": detection,
        }

    return {
        "success": True,
        "original_image": original_image,
        "annotated_image": annotated_image,
        "detection": detection,
        "report": cast(WasteReport, report_response),
    }


__all__ = [
    "AnalysisDetection",
    "WasteAnalysisFailure",
    "WasteAnalysisResponse",
    "WasteAnalysisResult",
    "analyze_waste_image",
]
