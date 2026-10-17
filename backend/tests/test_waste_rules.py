"""Behavioral tests for the active, versioned waste rules."""

import json

import pytest
from pydantic import ValidationError

from app.api.reports import ReportSubmission
from app.services.ai import waste_rules
from app.services.ai.waste_rules import WasteRuleError, classify_item, load_rules


def test_plastic_bottle_requires_confirmed_condition_and_station_acceptance():
    pending = classify_item("plastic bottle")
    assert pending["original_label"] == "plastic bottle"
    assert pending["canonical_item"] == "plastic_bottle"
    assert pending["material"] == "Plastic"
    assert pending["category"] is None
    assert pending["needs_confirmation"] is True
    assert pending["station_material_key"] == "Plastic"
    assert pending["rule_id"] == "WASTE-PLASTIC_BOTTLE-v1"

    confirmed = {"hazardous_contents": False, "empty_and_clean": True}
    assert classify_item("plastic bottle", answers=confirmed)["category"] is None
    assert classify_item("plastic bottle", answers=confirmed,
                         station_accepted_materials={"Metal"})["category"] is None
    accepted = classify_item("plastic bottle", answers=confirmed,
                             station_accepted_materials={"plastic"})
    assert accepted["category"] == "Recyclable Waste"
    assert accepted["needs_confirmation"] is False
    conflicting = classify_item("plastic bottle", confirmed_material="Glass", answers=confirmed,
                                station_accepted_materials={"Plastic"})
    assert conflicting["category"] is None
    assert "conflicts" in conflicting["confirmation_reason"]


def test_generic_bottle_does_not_become_plastic_without_user_material():
    generic = classify_item("Bottle")
    assert generic["original_label"] == "Bottle"
    assert generic["canonical_item"] == "bottle"
    assert generic["material"] is None
    assert generic["category"] is None
    assert generic["needs_confirmation"]
    assert classify_item("Bottle", confirmed_material="Glass")["canonical_item"] == "glass"
    assert classify_item("Bottle", confirmed_material="plastic")["canonical_item"] == "plastic_bottle"


def test_confirmed_hazardous_contents_override_recycling_and_bulky_handling():
    bottle = classify_item("plastic bottle", answers={"hazardous_contents": True},
                           station_accepted_materials={"Plastic"})
    assert bottle["category"] == "Hazardous Waste"
    assert bottle["station_material_key"] is None
    assert "ordinary recycling" in bottle["handling_guidance"]
    fridge = classify_item("refrigerator")
    assert fridge["category"] == "Hazardous Waste"
    assert fridge["bulky"] is True
    assert fridge["station_material_key"] is None


def test_battery_is_hazardous_without_guessing_its_chemistry():
    result = classify_item("batteries")
    assert result["canonical_item"] == "battery"
    assert result["category"] == "Hazardous Waste"
    assert result["material"] is None
    assert result["needs_confirmation"] is True
    assert result["station_material_key"] is None


def test_food_waste_and_sofa_take_separate_non_recycling_routes():
    food = classify_item("food scraps")
    sofa = classify_item("couch")
    assert food["category"] == "Non-Recyclable Waste"
    assert food["material"] == "Organic Material"
    assert food["station_material_key"] is None
    assert sofa["category"] == "Bulky Waste"
    assert sofa["bulky"] is True
    assert sofa["station_material_key"] is None


def test_electronic_waste_is_hazardous_and_unknown_identity_stays_unresolved():
    electronics = classify_item("e-waste")
    unknown = classify_item("ceramic plant pot", confirmed_material="Ceramic")
    assert electronics["category"] == "Hazardous Waste"
    assert electronics["station_material_key"] is None
    assert "authorised" in electronics["handling_guidance"]
    assert unknown["category"] is None
    assert unknown["needs_confirmation"] is True
    assert unknown["canonical_item"] == "ceramic_plant_pot"
    assert unknown["material"] == "Ceramic"
    assert unknown["rule_id"] == "WASTE-UNMAPPED-v1"


def test_rule_catalog_rejects_alias_collisions(tmp_path, monkeypatch):
    document = {"version": "test", "rules": {
        "one": {"display_name": "One", "aliases": ["same"], "material": "X",
                "category": "Non-Recyclable Waste", "questions": [],
                "handling_guidance": "Collect separately.", "station_material_key": None,
                "rule_id": "ONE-v1", "bulky": False, "guidance_source": "test"},
        "two": {"display_name": "Two", "aliases": ["same"], "material": "Y",
                "category": "Bulky Waste", "questions": [],
                "handling_guidance": "Arrange collection.", "station_material_key": None,
                "rule_id": "TWO-v1", "bulky": True, "guidance_source": "test"},
    }}
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(waste_rules, "RULES_PATH", path)
    load_rules.cache_clear()
    try:
        with pytest.raises(WasteRuleError, match="multiple rules"):
            load_rules()
    finally:
        load_rules.cache_clear()


def test_versioned_report_rejects_hazardous_item_as_ordinary_recyclable():
    payload = {
        "rule_version": "1.0.0", "reporter_role": "user", "title": "Found bottle",
        "summary": "A bottle with confirmed chemical contents was found.",
        "category": "Recyclable Waste",
        "confirmed_items": [{"name": "Plastic Bottle", "category": "Recyclable Waste",
                             "material": "Plastic", "condition_answers": {"hazardous_contents": True}}],
        "location": "Campus", "latitude": 6.4, "longitude": 100.2,
        "location_source": "map",
    }
    with pytest.raises(ValidationError, match="Hazardous Waste"):
        ReportSubmission.model_validate(payload)
    payload["category"] = "Hazardous Waste"
    payload["confirmed_items"][0]["category"] = "Hazardous Waste"
    assert ReportSubmission.model_validate(payload).category == "Hazardous Waste"
