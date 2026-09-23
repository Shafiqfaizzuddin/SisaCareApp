"""Reusable YOLO waste detection service."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from threading import Lock
from typing import Any, Literal, TypedDict

from app.services.ai.category_mapping import get_category_metadata
from app.services.ai.image_annotator import (
    ImageAnnotationError,
    save_annotated_image,
)
from app.services.ai.image_validation import (
    ImageNotFoundError,
    ImageValidationError,
    InvalidImageError,
    UnsupportedFileTypeError,
    validate_image,
)


DEFAULT_CONFIDENCE_THRESHOLD = 0.35
MODEL_PATH = Path(__file__).resolve().parents[4] / "ai" / "models" / "best.pt"

ErrorCode = Literal[
    "NO_WASTE_DETECTED",
    "IMAGE_NOT_FOUND",
    "INVALID_IMAGE",
    "UNSUPPORTED_FILE_TYPE",
    "MODEL_NOT_FOUND",
    "MODEL_LOAD_ERROR",
    "MODEL_INFERENCE_ERROR",
    "ANNOTATION_ERROR",
    "INVALID_CONFIDENCE_THRESHOLD",
    "DETECTION_ERROR",
]


class BoundingBox(TypedDict):
    x1: float
    y1: float
    x2: float
    y2: float


class WasteDetection(TypedDict):
    class_name: str
    class_id: int
    confidence: float
    bounding_box: BoundingBox
    display_name: str
    waste_category: str
    material: str
    recyclable: bool
    recommended_handling: str


class DetectionFailure(TypedDict):
    success: Literal[False]
    code: ErrorCode
    message: str


class WasteDetectionResult(TypedDict):
    success: Literal[True]
    code: Literal["WASTE_DETECTED"]
    message: str
    total_objects: int
    counts: dict[str, int]
    detections: list[WasteDetection]
    annotated_image_path: str


WasteDetectionResponse = WasteDetectionResult | DetectionFailure


class WasteDetectionError(RuntimeError):
    """Base exception for internal waste detection failures."""

    code: ErrorCode = "DETECTION_ERROR"
    public_message = "Waste detection failed unexpectedly."


class ModelNotFoundError(WasteDetectionError):
    """Raised when the configured YOLO model is missing."""

    code: ErrorCode = "MODEL_NOT_FOUND"
    public_message = "The waste detection model file is missing."


class ModelLoadError(WasteDetectionError):
    """Raised when Ultralytics cannot load the YOLO model."""

    code: ErrorCode = "MODEL_LOAD_ERROR"
    public_message = "The waste detection model could not be loaded."


class ModelInferenceError(WasteDetectionError):
    """Raised when YOLO inference or result parsing fails."""

    code: ErrorCode = "MODEL_INFERENCE_ERROR"
    public_message = "The waste detection model could not process this image."


class AnnotationCreationError(WasteDetectionError):
    """Raised when an annotated output image cannot be created."""

    code: ErrorCode = "ANNOTATION_ERROR"
    public_message = "The annotated image could not be created."


class InvalidConfidenceThresholdError(WasteDetectionError):
    """Raised when confidence is outside the inclusive 0-1 range."""

    code: ErrorCode = "INVALID_CONFIDENCE_THRESHOLD"
    public_message = "Confidence threshold must be a number between 0 and 1."


_model: Any | None = None
_model_lock = Lock()
_inference_lock = Lock()


def _failure(code: ErrorCode, message: str) -> DetectionFailure:
    return {"success": False, "code": code, "message": message}


def _validate_confidence_threshold(confidence_threshold: float) -> float:
    if isinstance(confidence_threshold, bool) or not isinstance(
        confidence_threshold, (int, float)
    ):
        raise InvalidConfidenceThresholdError()

    threshold = float(confidence_threshold)
    if not 0.0 <= threshold <= 1.0:
        raise InvalidConfidenceThresholdError()
    return threshold


def _load_model() -> Any:
    global _model

    if _model is not None:
        return _model

    with _model_lock:
        if _model is not None:
            return _model

        if not MODEL_PATH.is_file():
            raise ModelNotFoundError(f"YOLO model not found: {MODEL_PATH}")

        try:
            from ultralytics import YOLO

            _model = YOLO(str(MODEL_PATH))
        except Exception as exc:
            raise ModelLoadError(f"Failed to load YOLO model: {exc}") from exc

    return _model


def _class_name(names: dict[int, str] | list[str], class_id: int) -> str:
    if isinstance(names, dict):
        return names.get(class_id, f"class_{class_id}")
    if 0 <= class_id < len(names):
        return names[class_id]
    return f"class_{class_id}"


def _serialize_detections(results: Any) -> tuple[list[WasteDetection], dict[str, int]]:
    detections: list[WasteDetection] = []
    counts: Counter[str] = Counter()

    try:
        for result in results:
            if result.boxes is None:
                continue

            for box in result.boxes:
                class_id = int(box.cls.item())
                name = _class_name(result.names, class_id)
                metadata = get_category_metadata(name)
                x1, y1, x2, y2 = (float(value) for value in box.xyxy[0].tolist())

                detections.append(
                    {
                        "class_name": name,
                        "class_id": class_id,
                        "confidence": float(box.conf.item()),
                        **metadata,
                        "bounding_box": {
                            "x1": x1,
                            "y1": y1,
                            "x2": x2,
                            "y2": y2,
                        },
                    }
                )
                counts[name] += 1
    except Exception as exc:
        raise ModelInferenceError(f"Failed to parse YOLO results: {exc}") from exc

    return detections, dict(counts)


def _detect_waste(
    image_path: str | Path,
    confidence_threshold: float,
) -> WasteDetectionResponse:
    threshold = _validate_confidence_threshold(confidence_threshold)
    resolved_image_path = validate_image(image_path)
    model = _load_model()

    try:
        with _inference_lock:
            results = model.predict(
                source=str(resolved_image_path),
                conf=threshold,
                verbose=False,
            )
    except Exception as exc:
        raise ModelInferenceError(f"YOLO inference failed: {exc}") from exc

    if not results:
        return _failure(
            "NO_WASTE_DETECTED",
            "No supported waste objects were detected in this image.",
        )

    detections, counts = _serialize_detections(results)
    if not detections:
        return _failure(
            "NO_WASTE_DETECTED",
            "No supported waste objects were detected in this image.",
        )

    try:
        annotated_image_path = save_annotated_image(results[0], resolved_image_path)
    except ImageAnnotationError as exc:
        raise AnnotationCreationError(str(exc)) from exc

    return {
        "success": True,
        "code": "WASTE_DETECTED",
        "message": "Supported waste objects were detected successfully.",
        "total_objects": len(detections),
        "counts": counts,
        "detections": detections,
        "annotated_image_path": str(annotated_image_path),
    }


def detect_waste(
    image_path: str | Path,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> WasteDetectionResponse:
    """Detect waste and return an API-friendly success or failure response.

    The YOLO model is loaded lazily and reused for subsequent calls in the same
    process. Failure responses never contain a detections list, which prevents
    no-detection results from being forwarded to report generation.
    """

    try:
        return _detect_waste(image_path, confidence_threshold)
    except ImageValidationError as exc:
        return _failure(exc.code, exc.public_message)  # type: ignore[arg-type]
    except WasteDetectionError as exc:
        return _failure(exc.code, exc.public_message)
    except Exception:
        return _failure("DETECTION_ERROR", "Waste detection failed unexpectedly.")


__all__ = [
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "DetectionFailure",
    "ImageNotFoundError",
    "InvalidImageError",
    "UnsupportedFileTypeError",
    "WasteDetectionResponse",
    "WasteDetectionResult",
    "detect_waste",
]
