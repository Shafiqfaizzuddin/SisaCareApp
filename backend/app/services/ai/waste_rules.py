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
    canonical_item: str
    display_name: str
    material: str | None
    category: str | None
    needs_confirmation: bool
    confirmation_reason: str | None
    handling_guidance: str
    station_material_key: str | None
    rule_id: str
    bulky: bool
    questions: list[dict[str, str]]


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().casefold().replace("&", " ")).strip("_")


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
            and isinstance(question["key"], str) and question["key"] in RECYCLING_QUESTION_KEYS | {"hazardous_contents", "material"}
            and isinstance(question["prompt"], str) and question["prompt"].strip()
            for question in questions
        ):
            raise WasteRuleError(f"{canonical} has invalid confirmation questions.")
        if any(question["key"] == "hazardous_contents" for question in questions):
            if not isinstance(rule.get("hazardous_handling_guidance"), str) or not rule["hazardous_handling_guidance"].strip():
                raise WasteRuleError(f"{canonical} needs reviewed hazardous handling guidance.")
            if not isinstance(rule.get("hazardous_guidance_source"), str) or not rule["hazardous_guidance_source"].strip():
                raise WasteRuleError(f"{canonical} needs a hazardous guidance source.")
        rules[canonical] = rule
        for alias in (canonical, rule["display_name"], *rule["aliases"]):
            normalized = _key(alias)
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
) -> RuleResult:
    """Classify observed labels only from exact aliases and explicit user facts.

    Station acceptance is an exact, case-insensitive material-key match. A
    recyclable suggestion is unresolved until its condition questions and
    selected station are checked. Unknown items remain unresolved even when a
    material is supplied, because material alone does not establish identity.
    """
    if not isinstance(label, str) or not _key(label):
        raise ValueError("A nonempty object label is required.")
    rules, aliases = load_rules()
    canonical = aliases.get(_key(label), _key(label))
    facts = answers or {}
    supplied_material = confirmed_material.strip() if isinstance(confirmed_material, str) else None
    if canonical == "bottle" and supplied_material:
        material_key = supplied_material.casefold()
        if material_key in {"plastic", "pet"}:
            canonical = "plastic_bottle"
        elif material_key == "glass":
            canonical = "glass"
    rule = rules.get(canonical)
    if rule is None:
        return RuleResult(
            original_label=label, canonical_item=canonical,
            display_name=canonical.replace("_", " ").title(), material=supplied_material,
            category=None, needs_confirmation=True,
            confirmation_reason="The object identity is not in the maintained waste rules.",
            handling_guidance=UNKNOWN_GUIDANCE, station_material_key=None,
            rule_id="WASTE-UNMAPPED-v1", bulky=False, questions=[],
        )
    material = rule["material"]
    material_conflict = bool(supplied_material and material and _key(supplied_material) != _key(material))
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
    if "hazardous_contents" in question_keys and facts.get("hazardous_contents") is True:
        category = "Hazardous Waste"
        station_key = None
        guidance = rule["hazardous_handling_guidance"]
    elif category == "Recyclable Waste":
        missing = [question["prompt"] for question in questions
                   if question["key"] in RECYCLING_QUESTION_KEYS and facts.get(question["key"]) is not True]
        if "hazardous_contents" in question_keys and facts.get("hazardous_contents") is not False:
            missing.insert(0, "Confirm that the item did not contain hazardous substances.")
        if missing:
            category = None
            reason = " ".join(missing)
        elif station_key is None or station_accepted_materials is None or _key(station_key) not in {_key(value) for value in station_accepted_materials}:
            category = None
            reason = "Confirm that the selected recycling station accepts this material."

    if material_conflict:
        if category != "Hazardous Waste":
            category = None
        reason = (reason + " " if reason else "") + "The confirmed material conflicts with the item label."
    if material is None and category != "Hazardous Waste":
        category = None
    if category is None and reason is None:
        reason = "Confirm the item material and an appropriate disposal route."
    if material is None and (reason is None or "material" not in reason.casefold()):
        reason = (reason + " " if reason else "") + "Confirm the item's material."
    return RuleResult(
        original_label=label, canonical_item=canonical,
        display_name=rule["display_name"], material=material,
        category=category, needs_confirmation=reason is not None,
        confirmation_reason=reason, handling_guidance=guidance,
        station_material_key=station_key, rule_id=rule["rule_id"],
        bulky=rule["bulky"], questions=questions,
    )


__all__ = ["FINAL_CATEGORIES", "RULES_PATH", "WasteRuleError", "RuleResult", "classify_item", "load_rules"]
