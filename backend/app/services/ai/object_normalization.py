"""Conservative, alias-based normalization for YOLO and VLM object labels."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import TypedDict


MAPPING_PATH = (
    Path(__file__).resolve().parents[4] / "ai" / "config" / "object_names.json"
)
CANONICAL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")


class ObjectNameDefinition(TypedDict):
    display_name: str
    aliases: list[str]


class NormalizedObjectName(TypedDict):
    canonical_name: str
    display_name: str
    known: bool


class ObjectNameMappingError(RuntimeError):
    """Raised when the controlled object-name mapping is invalid."""


def normalize_label_format(label: str) -> str:
    """Normalize case and separators without guessing synonyms or spelling."""

    if not isinstance(label, str):
        raise TypeError("Object label must be a string.")
    normalized = label.strip().casefold().replace("&", " ")
    return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")


def _validate_definition(
    canonical_name: str,
    value: object,
) -> ObjectNameDefinition:
    if not isinstance(value, dict) or set(value) != {"display_name", "aliases"}:
        raise ObjectNameMappingError(
            f"Mapping for '{canonical_name}' requires display_name and aliases only."
        )

    display_name = value.get("display_name")
    if not isinstance(display_name, str) or not display_name.strip():
        raise ObjectNameMappingError(
            f"Mapping for '{canonical_name}' requires a non-empty display_name."
        )
    aliases = value.get("aliases")
    if not isinstance(aliases, list) or not all(
        isinstance(alias, str) and alias.strip() for alias in aliases
    ):
        raise ObjectNameMappingError(
            f"Mapping for '{canonical_name}' requires a list of non-empty aliases."
        )
    return {
        "display_name": display_name.strip(),
        "aliases": list(dict.fromkeys(alias.strip() for alias in aliases)),
    }


@lru_cache(maxsize=1)
def _load_registry() -> tuple[
    dict[str, ObjectNameDefinition],
    dict[str, str],
]:
    if not MAPPING_PATH.is_file():
        raise ObjectNameMappingError(f"Object-name mapping not found: {MAPPING_PATH}")
    try:
        raw_mapping = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ObjectNameMappingError(
            f"Failed to load object-name mapping: {exc}"
        ) from exc
    if not isinstance(raw_mapping, dict):
        raise ObjectNameMappingError("Object-name mapping must be a JSON object.")

    definitions: dict[str, ObjectNameDefinition] = {}
    alias_index: dict[str, str] = {}
    for raw_canonical_name, raw_definition in raw_mapping.items():
        if not isinstance(raw_canonical_name, str):
            raise ObjectNameMappingError("Canonical object names must be strings.")
        canonical_name = raw_canonical_name.strip()
        if (
            not CANONICAL_NAME_PATTERN.fullmatch(canonical_name)
            or normalize_label_format(canonical_name) != canonical_name
        ):
            raise ObjectNameMappingError(
                f"Canonical name '{raw_canonical_name}' must use lowercase snake_case."
            )
        definition = _validate_definition(canonical_name, raw_definition)
        definitions[canonical_name] = definition

        controlled_labels = (
            canonical_name,
            definition["display_name"],
            *definition["aliases"],
        )
        for label in controlled_labels:
            normalized_alias = normalize_label_format(label)
            if not normalized_alias:
                raise ObjectNameMappingError(
                    f"Mapping for '{canonical_name}' contains an unusable alias."
                )
            existing = alias_index.get(normalized_alias)
            if existing is not None and existing != canonical_name:
                raise ObjectNameMappingError(
                    f"Alias '{label}' conflicts between '{existing}' and "
                    f"'{canonical_name}'."
                )
            alias_index[normalized_alias] = canonical_name
    return definitions, alias_index


def load_object_name_mapping() -> dict[str, ObjectNameDefinition]:
    """Return a caller-safe copy of all canonical names and controlled aliases."""

    definitions, _alias_index = _load_registry()
    return {
        canonical_name: {
            "display_name": definition["display_name"],
            "aliases": definition["aliases"].copy(),
        }
        for canonical_name, definition in definitions.items()
    }


def reload_object_name_mapping() -> dict[str, ObjectNameDefinition]:
    """Clear the cached registry and reload the editable JSON mapping."""

    _load_registry.cache_clear()
    return load_object_name_mapping()


def normalize_object_name(label: str) -> str:
    """Return an exact controlled canonical name or a conservative fallback."""

    normalized_label = normalize_label_format(label)
    if not normalized_label:
        raise ValueError("Object label must contain letters or numbers.")
    _definitions, alias_index = _load_registry()
    return alias_index.get(normalized_label, normalized_label)


def get_object_display_name(label: str) -> str:
    """Return the controlled display name, or a deterministic unknown fallback."""

    canonical_name = normalize_object_name(label)
    definitions, _alias_index = _load_registry()
    definition = definitions.get(canonical_name)
    if definition is not None:
        return definition["display_name"]
    return canonical_name.replace("_", " ").title()


def normalize_object(label: str) -> NormalizedObjectName:
    """Return canonical and display forms plus whether an explicit mapping matched."""

    canonical_name = normalize_object_name(label)
    definitions, _alias_index = _load_registry()
    definition = definitions.get(canonical_name)
    return {
        "canonical_name": canonical_name,
        "display_name": (
            definition["display_name"]
            if definition is not None
            else canonical_name.replace("_", " ").title()
        ),
        "known": definition is not None,
    }


__all__ = [
    "MAPPING_PATH",
    "NormalizedObjectName",
    "ObjectNameDefinition",
    "ObjectNameMappingError",
    "get_object_display_name",
    "load_object_name_mapping",
    "normalize_label_format",
    "normalize_object",
    "normalize_object_name",
    "reload_object_name_mapping",
]
