import json

from app.api.reports import ReportSubmission
from app.repositories.reports import _build_review_confirmation
from app.services.ai.waste_rules import classify_item


def _observation(label="bottle", category=None, material="Unknown"):
    raw = {"id": "det-1", "label": label, "material": material, "suggested_category": category}
    review = {"id": "det-1", "source_detection_id": "det-1", "disposition": "needs_confirmation" if category is None else "waste",
              "corrected_label": label, "material": material, "category": category, "quantity": None,
              "condition_answers": {}, "component_relation": None}
    item = {"review_id": "det-1", "name": label, "material": material, "category": category,
            "quantity": None, "condition_answers": {}}
    return json.dumps({"provider": "florence2", "raw_detections": [raw]}), {
        "reviewed_detections": [review], "confirmed_items": [item], "split_recycling_review_ids": []}


def test_uncertain_model_observation_remains_reportable_without_user_confirmation():
    raw, payload = _observation()
    result = _build_review_confirmation(raw, payload)
    assert result["final_confirmed_items"][0]["category"] is None
    assert result["final_confirmed_items"][0]["classification_state"] == "needs_confirmation"
    assert result["final_confirmed_items"][0]["independently_verified"] is False
    assert result["user_corrections"][0]["original_label"] == "bottle"


def test_no_detections_can_be_reported_for_admin_assessment():
    result = _build_review_confirmation(json.dumps({"provider": "florence2", "raw_detections": []}), {
        "reviewed_detections": [], "confirmed_items": [], "split_recycling_review_ids": []})
    assert result["final_confirmed_items"] == []


def test_report_accepts_uncertain_items_as_review_state():
    submission = ReportSubmission.model_validate({
        "reporter_role": "user", "title": "Unidentified waste", "summary": "Waste is visible but the material is unclear.",
        "category": "Needs Confirmation", "confirmed_items": [{"name": "bottle", "category": None}],
        "location": "Community Hall", "latitude": 6.4, "longitude": 100.2, "location_source": "map",
        "rule_version": "1.2.0",
    })
    assert submission.category == "Needs Confirmation"


def test_explicit_discarded_mattress_is_bulky_but_ordinary_sofa_is_uncertain():
    assert classify_item("discarded mattress")["category"] == "Bulky Waste"
    assert classify_item("sofa")["category"] is None
