"""Deterministic fusion of normalized YOLO detections and VLM observations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal, TypedDict, cast

from app.services.ai.category_mapping import (
    CategorySource,
    VLM_WASTE_CATEGORIES,
    WasteCategory,
    classify_waste_object,
)
from app.services.ai.object_normalization import normalize_object
from app.services.ai.vlm_analyzer import ConfidenceLevel, VlmObject
from app.services.ai.yolo_detector import BoundingBox, WasteDetection


FusionSource = Literal["yolo", "vlm", "yolo+vlm"]
CONFIDENCE_LEVEL_RANK: dict[ConfidenceLevel, int] = {
    "low": 0,
    "medium": 1,
    "high": 2,
}


class FusedWasteObject(TypedDict):
    name: str
    display_name: str
    category: WasteCategory
    category_source: CategorySource
    source: FusionSource
    confidence: float | None
    confidence_level: ConfidenceLevel | None
    supported_by_vlm: bool
    bounding_box: BoundingBox | None


class FusionInputError(ValueError):
    """Raised when fusion receives data outside the detector contracts."""


class _NormalizedVlmObservation(TypedDict):
    name: str
    display_name: str
    suggested_category: WasteCategory
    confidence_level: ConfidenceLevel


def _required_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FusionInputError(f"{field} must be a non-empty string.")
    return value.strip()


def _validate_confidence(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FusionInputError(f"{field} must be a number between 0 and 1.")
    confidence = float(value)
    if not 0.0 <= confidence <= 1.0:
        raise FusionInputError(f"{field} must be a number between 0 and 1.")
    return confidence


def _copy_bounding_box(value: object, field: str) -> BoundingBox:
    required_coordinates = {"x1", "y1", "x2", "y2"}
    if not isinstance(value, Mapping) or set(value) != required_coordinates:
        raise FusionInputError(
            f"{field} must contain exactly x1, y1, x2, and y2."
        )

    coordinates: dict[str, float] = {}
    for coordinate in ("x1", "y1", "x2", "y2"):
        raw_coordinate = value[coordinate]
        if isinstance(raw_coordinate, bool) or not isinstance(
            raw_coordinate, (int, float)
        ):
            raise FusionInputError(f"{field}.{coordinate} must be numeric.")
        coordinates[coordinate] = float(raw_coordinate)

    if (
        coordinates["x2"] < coordinates["x1"]
        or coordinates["y2"] < coordinates["y1"]
    ):
        raise FusionInputError(f"{field} has invalid coordinate ordering.")

    return cast(BoundingBox, coordinates)


def _normalize_vlm_observations(
    observations: Sequence[VlmObject],
) -> dict[str, _NormalizedVlmObservation]:
    normalized_observations: dict[str, _NormalizedVlmObservation] = {}

    for index, observation in enumerate(observations):
        if not isinstance(observation, Mapping):
            raise FusionInputError(f"vlm_observations[{index}] must be an object.")
        raw_name = _required_string(
            observation.get("name"),
            f"vlm_observations[{index}].name",
        )
        confidence_level = observation.get("confidence_level")
        if confidence_level not in CONFIDENCE_LEVEL_RANK:
            raise FusionInputError(
                f"vlm_observations[{index}].confidence_level must be high, "
                "medium, or low."
            )
        suggested_category = observation.get("suggested_category")
        if suggested_category not in VLM_WASTE_CATEGORIES:
            raise FusionInputError(
                f"vlm_observations[{index}].suggested_category is not allowed."
            )

        normalized = normalize_object(raw_name)
        canonical_name = normalized["canonical_name"]
        candidate: _NormalizedVlmObservation = {
            "name": canonical_name,
            "display_name": normalized["display_name"],
            "suggested_category": cast(WasteCategory, suggested_category),
            "confidence_level": cast(ConfidenceLevel, confidence_level),
        }
        existing = normalized_observations.get(canonical_name)
        if existing is None or (
            CONFIDENCE_LEVEL_RANK[candidate["confidence_level"]]
            > CONFIDENCE_LEVEL_RANK[existing["confidence_level"]]
        ):
            normalized_observations[canonical_name] = candidate

    return normalized_observations


def fuse_waste_objects(
    yolo_detections: Sequence[WasteDetection],
    vlm_observations: Sequence[VlmObject],
) -> list[FusedWasteObject]:
    """Fuse detector facts without replacing instances or inventing geometry.

    VLM agreement supports every YOLO instance with the same canonical name.
    A normalized VLM name already represented by YOLO does not create another
    object. Distinct VLM observations remain as box-free records.
    """

    normalized_vlm = _normalize_vlm_observations(vlm_observations)
    yolo_names: set[str] = set()
    fused_objects: list[FusedWasteObject] = []

    for index, detection in enumerate(yolo_detections):
        if not isinstance(detection, Mapping):
            raise FusionInputError(f"yolo_detections[{index}] must be an object.")
        raw_name = _required_string(
            detection.get("class_name"),
            f"yolo_detections[{index}].class_name",
        )
        confidence = _validate_confidence(
            detection.get("confidence"),
            f"yolo_detections[{index}].confidence",
        )
        bounding_box = _copy_bounding_box(
            detection.get("bounding_box"),
            f"yolo_detections[{index}].bounding_box",
        )
        normalized = normalize_object(raw_name)
        canonical_name = normalized["canonical_name"]
        vlm_observation = normalized_vlm.get(canonical_name)
        classification = classify_waste_object(
            canonical_name,
            (
                vlm_observation["suggested_category"]
                if vlm_observation is not None
                else None
            ),
        )
        yolo_names.add(canonical_name)
        fused_objects.append(
            {
                "name": classification["name"],
                "display_name": classification["display_name"],
                "category": classification["category"],
                "category_source": classification["category_source"],
                "source": "yolo+vlm" if vlm_observation is not None else "yolo",
                "confidence": confidence,
                "confidence_level": None,
                "supported_by_vlm": vlm_observation is not None,
                "bounding_box": bounding_box,
            }
        )

    for canonical_name, observation in normalized_vlm.items():
        if canonical_name in yolo_names:
            continue
        classification = classify_waste_object(
            canonical_name,
            observation["suggested_category"],
        )
        fused_objects.append(
            {
                "name": classification["name"],
                "display_name": classification["display_name"],
                "category": classification["category"],
                "category_source": classification["category_source"],
                "source": "vlm",
                "confidence": None,
                "confidence_level": observation["confidence_level"],
                "supported_by_vlm": False,
                "bounding_box": None,
            }
        )

    return fused_objects


__all__ = [
    "FusedWasteObject",
    "FusionInputError",
    "FusionSource",
    "fuse_waste_objects",
]
