"""Small, deterministic waste rules for Florence labels and confirmed facts.

The active rule catalog is ai/config/waste_rules.json. Legacy YOLO mappings are
retained separately for historical comparison and are not consulted here.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, TypedDict


RULES_PATH = Path(__file__).resolve().parents[4] / "ai" / "config" / "waste_rules.json"
FINAL_CATEGORIES = frozenset({
    "Recyclable Waste", "Non-Recyclable Waste", "Bulky Waste", "Hazardous Waste"
})
RECYCLING_QUESTION_KEYS = frozenset({"empty_and_clean", "clean_and_dry"})
UNKNOWN_GUIDANCE = "Confirm the item and material before choosing a disposal route."


class WasteRuleError(ValueError):
    """The maintained rule catalog is missing or inconsistent."""


class RuleResult(TypedDict):
    original_label: str
    canonical_name: str
    canonical_item: str
    display_name: str
    material: str | None
    category: str | None
    waste_category: str | None
    needs_confirmation: bool
    confirmation_question: str | None
    confirmation_reason: str | None
    handling_guidance: str
    station_material_key: str | None
    rule_id: str | None
    classification_source: str
    bulky: bool
    questions: list[dict[str, str]]


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().casefold().replace("&", " ")).strip("_")


def normalize_label(value: str) -> str:
    """Public, exact-match key shared by detection and rule lookup."""
    return _key(value)


def _forms(value: str) -> set[str]:
    """Only ordinary final-word inflections, never fuzzy or substring matches."""
    key = _key(value)
    forms = {key}
    parts = key.rsplit("_", 1)
    stem, word = (parts[0] + "_", parts[1]) if len(parts) == 2 else ("", parts[0])
    if len(word) > 2:
        if word.endswith("ies"):
            forms.add(stem + word[:-3] + "y")
        elif word.endswith(("ches", "shes", "xes")):
            forms.add(stem + word[:-2])
        elif word.endswith("s") and not word.endswith(("ss", "us")):
            forms.add(stem + word[:-1])
        elif word.endswith("y"):
            forms.add(stem + word[:-1] + "ies")
        elif word.endswith(("ch", "sh", "x")):
            forms.add(stem + word + "es")
        else:
            forms.add(stem + word + "s")
    return forms


def _material_key(value: str) -> str:
    key = _key(value)
    return {"pet": "plastic", "aluminum": "metal", "aluminium": "metal"}.get(key, key)


@lru_cache(maxsize=1)
def load_rules() -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Load and validate the sole active catalog, including alias collisions."""
    try:
        document = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WasteRuleError("The waste rule catalog could not be read.") from exc
    if not isinstance(document, dict) or not isinstance(document.get("version"), str) or not isinstance(document.get("rules"), dict):
        raise WasteRuleError("The waste rule catalog needs a version and rules object.")
    rules: dict[str, dict[str, Any]] = {}
    aliases: dict[str, str] = {}
    rule_ids: set[str] = set()
    for canonical, rule in document["rules"].items():
        if not isinstance(canonical, str) or _key(canonical) != canonical or not isinstance(rule, dict):
            raise WasteRuleError("Each rule needs a canonical snake-case item name.")
        if not isinstance(rule.get("display_name"), str) or not rule["display_name"].strip():
            raise WasteRuleError(f"{canonical} needs a display name.")
        if not isinstance(rule.get("aliases"), list) or not all(isinstance(alias, str) and _key(alias) for alias in rule["aliases"]):
            raise WasteRuleError(f"{canonical} needs nonempty aliases.")
        for field in ("material", "category", "station_material_key"):
            if rule.get(field) is not None and (not isinstance(rule[field], str) or not rule[field].strip()):
                raise WasteRuleError(f"{canonical} has an invalid {field}.")
        if rule.get("category") is not None and rule["category"] not in FINAL_CATEGORIES:
            raise WasteRuleError(f"{canonical} has an unsupported final category.")
        if rule.get("category") == "Hazardous Waste" and rule.get("station_material_key") is not None:
            raise WasteRuleError(f"{canonical} cannot send hazardous waste to an ordinary station.")
        if not isinstance(rule.get("bulky"), bool):
            raise WasteRuleError(f"{canonical} needs a bulky flag.")
        for field in ("handling_guidance", "guidance_source", "rule_id"):
            if not isinstance(rule.get(field), str) or not rule[field].strip():
                raise WasteRuleError(f"{canonical} needs {field}.")
        if rule["rule_id"] in rule_ids:
            raise WasteRuleError(f"Duplicate rule identifier: {rule['rule_id']}.")
        rule_ids.add(rule["rule_id"])
        questions = rule.get("questions")
        if not isinstance(questions, list) or not all(
            isinstance(question, dict) and set(question) == {"key", "prompt"}
            and isinstance(question["key"], str) and question["key"] in RECYCLING_QUESTION_KEYS | {"hazardous_contents", "material", "discarded", "packaging_type"}
            and isinstance(question["prompt"], str) and question["prompt"].strip()
            for question in questions
        ):
            raise WasteRuleError(f"{canonical} has invalid confirmation questions.")
        if any(question["key"] == "hazardous_contents" for question in questions):
            if not isinstance(rule.get("hazardous_handling_guidance"), str) or not rule["hazardous_handling_guidance"].strip():
                raise WasteRuleError(f"{canonical} needs reviewed hazardous handling guidance.")
            if not isinstance(rule.get("hazardous_guidance_source"), str) or not rule["hazardous_guidance_source"].strip():
                raise WasteRuleError(f"{canonical} needs a hazardous guidance source.")
        # The catalog's questions are the explicit classification conditions.
        # A null category also requires identity or material confirmation.
        rule["classification_conditions"] = questions
        rule["requires_user_confirmation"] = bool(questions or rule["category"] is None)
        rules[canonical] = rule
        for alias in (canonical, rule["display_name"], *rule["aliases"]):
            for normalized in _forms(alias):
                if normalized in aliases and aliases[normalized] != canonical:
                    raise WasteRuleError(f"Alias {alias!r} belongs to multiple rules.")
                aliases[normalized] = canonical
    return rules, aliases


def classify_item(
    label: str,
    *,
    confirmed_material: str | None = None,
    answers: Mapping[str, bool] | None = None,
    station_accepted_materials: set[str] | None = None,
    user_confirmed: bool = False,
) -> RuleResult:
    """Classify observed labels only from exact aliases and explicit user facts.

    Category is an item handling class. Station compatibility is a separate
    exact-key check and never determines that class.
    """
    if not isinstance(label, str) or not _key(label):
        raise ValueError("A nonempty object label is required.")
    rules, aliases = load_rules()
    normalized = _key(label)
    canonical = aliases.get(normalized, normalized)
    facts = answers or {}
    supplied_material = confirmed_material.strip() if isinstance(confirmed_material, str) else None
    if canonical == "bottle" and supplied_material:
        material_key = supplied_material.casefold()
        if material_key in {"plastic", "pet"}:
            canonical = "plastic_bottle"
        elif material_key == "glass":
            canonical = "glass_container"
    rule = rules.get(canonical)
    if rule is None:
        return RuleResult(
            original_label=label, canonical_name=canonical, canonical_item=canonical,
            display_name=canonical.replace("_", " ").title(), material=supplied_material,
            category=None, waste_category=None, needs_confirmation=True,
            confirmation_question="What is this item and what material is it made from?",
            confirmation_reason="The object identity is not in the maintained waste rules.",
            handling_guidance=UNKNOWN_GUIDANCE, station_material_key=None,
            rule_id=None, classification_source="user_confirmed" if user_confirmed else "rule",
            bulky=False, questions=[],
        )
    material = rule["material"]
    material_conflict = bool(supplied_material and material and _material_key(supplied_material) != _material_key(material))
    if supplied_material and material is None:
        material = supplied_material
    questions = [dict(question) for question in rule["questions"]]
    question_keys = {question["key"] for question in questions}
    category = rule["category"]
    station_key = rule["station_material_key"]
    guidance = rule["handling_guidance"]
    reason: str | None = None

    # A user-confirmed hazardous content or property overrides recyclable and
    # bulky handling. A bare detection label never supplies this fact.
    if facts.get("hazardous_contents") is True:
        category = "Hazardous Waste"
        station_key = None
        guidance = rule.get("hazardous_handling_guidance") or "Keep separate from ordinary recycling. Ask the relevant collection team for safe handling; do not open, puncture, empty or dismantle it."
    elif category == "Recyclable Waste":
        missing = [question["prompt"] for question in questions
                   if question["key"] in RECYCLING_QUESTION_KEYS and facts.get(question["key"]) is None]
        if "hazardous_contents" in question_keys and facts.get("hazardous_contents") is None:
            missing.insert(0, "Confirm whether this item contained hazardous substances.")
        if missing:
            reason = " ".join(missing)
        elif any(facts.get(key) is False for key in RECYCLING_QUESTION_KEYS & question_keys):
            category = None
            station_key = None
            reason = "The confirmed condition does not establish an ordinary recycling route. Confirm local disposal."
        elif station_accepted_materials is not None and (station_key is None or _key(station_key) not in {_key(value) for value in station_accepted_materials}):
            reason = "The selected recycling station does not accept this material."

    explicitly_discarded = normalized.startswith("discarded_") and normalized in aliases
    if category == "Bulky Waste" and "discarded" in question_keys and facts.get("discarded") is not True and not explicitly_discarded:
        category = None
        reason = "Confirm that this furniture is discarded waste, not furniture in use."

    if material_conflict:
        if category != "Hazardous Waste":
            category = None
        reason = (reason + " " if reason else "") + "The confirmed material conflicts with the item label."
    if category is None and reason is None:
        reason = "Confirm the item material and an appropriate disposal route."
    if material is None and category is None and (reason is None or "material" not in reason.casefold()):
        reason = (reason + " " if reason else "") + "Confirm the item's material."
    return RuleResult(
        original_label=label, canonical_name=canonical, canonical_item=canonical,
        display_name=rule["display_name"], material=material,
        category=category, waste_category=category, needs_confirmation=reason is not None,
        confirmation_question=reason,
        confirmation_reason=reason, handling_guidance=guidance,
        station_material_key=station_key, rule_id=rule["rule_id"],
        classification_source="user_confirmed" if user_confirmed else "rule",
        bulky=rule["bulky"], questions=questions,
    )


__all__ = ["FINAL_CATEGORIES", "RULES_PATH", "WasteRuleError", "RuleResult", "classify_item", "load_rules", "normalize_label"]
