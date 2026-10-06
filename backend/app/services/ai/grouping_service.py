"""Presentation-only grouping for classified fused waste objects."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import TypedDict, cast

from app.services.ai.category_mapping import WasteCategory
from app.services.ai.fusion_service import FusedWasteObject


LABEL_MAPPING_PATH = (
    Path(__file__).resolve().parents[4] / "ai" / "config" / "group_labels.json"
)
SOURCE_ORDER = ("yolo", "vlm")


class GroupLabels(TypedDict):
    single: str
    multiple: str


class GroupedWasteObject(TypedDict):
    name: str
    label: str
    count: int | None
    category: WasteCategory
    sources: list[str]
    average_yolo_confidence: float | None


class GroupedObjectsResult(TypedDict):
    grouped_objects: list[GroupedWasteObject]


class GroupingConfigurationError(RuntimeError):
    """Raised when explicit group labels cannot be loaded safely."""


class GroupingInputError(ValueError):
    """Raised when fused objects contain inconsistent grouping facts."""


@lru_cache(maxsize=1)
def load_group_labels() -> dict[str, GroupLabels]:
    if not LABEL_MAPPING_PATH.is_file():
        raise GroupingConfigurationError(
            f"Group-label mapping not found: {LABEL_MAPPING_PATH}"
        )
    try:
        raw_mapping = json.loads(LABEL_MAPPING_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GroupingConfigurationError(
            f"Failed to load group-label mapping: {exc}"
        ) from exc
    if not isinstance(raw_mapping, dict):
        raise GroupingConfigurationError("Group-label mapping must be a JSON object.")

    mapping: dict[str, GroupLabels] = {}
    for name, raw_labels in raw_mapping.items():
        if not isinstance(name, str) or not name.strip():
            raise GroupingConfigurationError(
                "Group-label mapping keys must be non-empty strings."
            )
        if not isinstance(raw_labels, dict) or set(raw_labels) != {
            "single",
            "multiple",
        }:
            raise GroupingConfigurationError(
                f"Group labels for '{name}' require single and multiple only."
            )
        single = raw_labels.get("single")
        multiple = raw_labels.get("multiple")
        if (
            not isinstance(single, str)
            or not single.strip()
            or not isinstance(multiple, str)
            or not multiple.strip()
        ):
            raise GroupingConfigurationError(
                f"Group labels for '{name}' must be non-empty strings."
            )
        mapping[name.strip()] = {
            "single": single.strip(),
            "multiple": multiple.strip(),
        }
    return mapping


def reload_group_labels() -> dict[str, GroupLabels]:
    load_group_labels.cache_clear()
    return load_group_labels()


def _sources_for_object(item: Mapping[str, object]) -> set[str]:
    if item["source"] == "yolo+vlm":
        return {"yolo", "vlm"}
    return {item["source"]}


def group_fused_objects(
    objects: Sequence[FusedWasteObject],
) -> GroupedObjectsResult:
    """Group for summaries without changing raw detections or their boxes."""

    labels = load_group_labels()
    grouped: dict[str, dict[str, object]] = {}

    for index, item in enumerate(objects):
        if not isinstance(item, Mapping):
            raise GroupingInputError(f"objects[{index}] must be an object.")
        name = item.get("name")
        display_name = item.get("display_name")
        category = item.get("category")
        source = item.get("source")
        if not isinstance(name, str) or not name:
            raise GroupingInputError(f"objects[{index}] requires a name.")
        if not isinstance(display_name, str) or not display_name:
            raise GroupingInputError(f"objects[{index}] requires a display_name.")
        if category not in {
            "Non-Recyclable",
            "Recyclable Waste",
            "Bulky Waste",
            "Unknown",
        }:
            raise GroupingInputError(f"objects[{index}] has an invalid category.")
        if source not in {"yolo", "vlm", "yolo+vlm"}:
            raise GroupingInputError(f"objects[{index}] has an invalid source.")

        existing = grouped.get(name)
        if existing is None:
            existing = {
                "display_name": display_name,
                "category": category,
                "sources": set(),
                "yolo_confidences": [],
                "exact_count": 0,
                "has_vlm_only": False,
            }
            grouped[name] = existing
        elif existing["category"] != category:
            raise GroupingInputError(
                f"Objects named '{name}' have conflicting final categories."
            )

        item_sources = _sources_for_object(item)
        existing_sources = existing["sources"]
        if isinstance(existing_sources, set):
            existing_sources.update(item_sources)

        if source in {"yolo", "yolo+vlm"}:
            confidence = item.get("confidence")
            if isinstance(confidence, bool) or not isinstance(
                confidence, (int, float)
            ):
                raise GroupingInputError(
                    f"YOLO-backed objects[{index}] requires numeric confidence."
                )
            confidences = existing["yolo_confidences"]
            if isinstance(confidences, list):
                confidences.append(float(confidence))
            exact_count = existing["exact_count"]
            if isinstance(exact_count, int):
                existing["exact_count"] = exact_count + 1
        else:
            existing["has_vlm_only"] = True

    output: list[GroupedWasteObject] = []
    for name, values in grouped.items():
        exact_count = values["exact_count"]
        has_vlm_only = values["has_vlm_only"] is True
        count = exact_count if isinstance(exact_count, int) and exact_count > 0 else None
        display_name = str(values["display_name"])
        configured_labels = labels.get(name)
        if count is not None and count >= 2:
            label = (
                configured_labels["multiple"]
                if configured_labels is not None
                else f"Pile of {display_name} Items"
            )
        else:
            label = (
                configured_labels["single"]
                if configured_labels is not None
                else display_name
            )

        confidences = values["yolo_confidences"]
        average_confidence = (
            round(sum(confidences) / len(confidences), 4)
            if isinstance(confidences, list) and confidences
            else None
        )
        source_values = values["sources"]
        sources = (
            [source for source in SOURCE_ORDER if source in source_values]
            if isinstance(source_values, set)
            else []
        )
        if has_vlm_only and count is None:
            average_confidence = None

        output.append(
            {
                "name": name,
                "label": label,
                "count": count,
                "category": cast(WasteCategory, values["category"]),
                "sources": sources,
                "average_yolo_confidence": average_confidence,
            }
        )

    return {"grouped_objects": output}


__all__ = [
    "GroupLabels",
    "GroupedObjectsResult",
    "GroupedWasteObject",
    "GroupingConfigurationError",
    "GroupingInputError",
    "group_fused_objects",
    "load_group_labels",
    "reload_group_labels",
]
