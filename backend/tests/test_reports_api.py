import base64
import json
import sqlite3
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.api import reports as reports_api
from app.core.config import Settings
from app.core.auth import get_optional_authenticated_user, require_admin_user
from app.repositories import reports as report_repository
from app.repositories import identities as identity_repository


client = TestClient(app)
MEMBER_USER = {
    "id": "usr-204",
    "email": "member@example.com",
    "role": "user",
    "email_verified": True,
    "google_sub": None,
    "google_email": None,
    "has_email_identity": True,
    "has_google_provider": False,
}
ADMIN_USER = {
    "id": "admin-1",
    "email": "admin@example.com",
    "role": "admin",
    "email_verified": True,
    "google_sub": None,
    "google_email": None,
    "has_email_identity": True,
    "has_google_provider": False,
}


@pytest.fixture(autouse=True)
def authenticated_api_users(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(identity_repository, "get_settings", lambda: Settings(
        _env_file=None, database_path=tmp_path / "identities.db",
    ))
    app.dependency_overrides[get_optional_authenticated_user] = lambda: MEMBER_USER
    app.dependency_overrides[require_admin_user] = lambda: ADMIN_USER
    yield
    app.dependency_overrides.clear()

DETECTIONS = [
    {
        "class_name": "plastic_bottle",
        "display_name": "Plastic Bottle",
        "waste_category": "Recyclable Waste",
        "material": "Plastic",
        "confidence": 0.9,
        "source": "yolo",
        "bounding_box": {
            "x1": 10.0,
            "y1": 20.0,
            "x2": 110.0,
            "y2": 220.0,
        },
    },
    {
        "class_name": "metal_can",
        "display_name": "Metal Can",
        "waste_category": "Recyclable Waste",
        "material": "Metal",
        "confidence": 0.84,
        "source": "yolo",
        "bounding_box": {
            "x1": 250.0,
            "y1": 40.0,
            "x2": 310.0,
            "y2": 160.0,
        },
    },
]

VLM_DETECTION = {
    "class_name": "mattress",
    "display_name": "Mattress",
    "waste_category": "Bulky Waste",
    "material": "Mixed Materials",
    "confidence": None,
    "bounding_box": None,
    "source": "vlm",
}

GENERATED_REPORT = {
    "title": "Generated municipal report",
    "summary": "Generated summary based on the detected waste.",
    "waste_identified": "One plastic bottle and one metal can.",
    "recommended_action": "Collect and route both items for recycling.",
    "environmental_concern": "The items may contribute to local litter.",
}

VALID_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def configure_report_storage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(report_repository, "DATABASE_PATH", tmp_path / "reports.db")
    monkeypatch.setattr(report_repository, "REPORT_ASSETS_DIR", tmp_path / "assets")


def create_draft(tmp_path: Path) -> str:
    original = tmp_path / "upload.jpg"
    annotated = tmp_path / "annotated.jpg"
    original.write_bytes(b"original image")
    annotated.write_bytes(b"annotated image")
    return report_repository.create_analysis_draft(
        original_image_path=original,
        annotated_image_path=annotated,
        detection={
            "detections": [*DETECTIONS, VLM_DETECTION],
            "raw_yolo": {
                "available": True,
                "error": None,
            },
            "raw_vlm": {
                "available": True,
                "scene_description": "Two recyclable items are visible.",
                "error": None,
            },
            "analysis": {
                "mode": "hybrid",
                "categories_detected": ["Recyclable Waste", "Bulky Waste"],
            },
        },
        report=GENERATED_REPORT,
        user_id=MEMBER_USER["id"],
    )


def submission_payload(draft_id: str | None) -> dict[str, Any]:
    return {
        "analysis_id": draft_id,
        "reporter_role": "user",
        "user_id": MEMBER_USER["id"],
        "guest_name": None,
        "guest_email": None,
        "title": "Reviewed waste report",
        "summary": "The user-edited final summary.",
        "waste_identified": "One plastic bottle.",
        "recommended_action": "Collect and recycle it.",
        "environmental_concern": "It may contribute to litter.",
        "category": "Recyclable Waste",
        "confirmed_items": [{"name": "Plastic Bottle", "category": "Recyclable Waste", "material": "Plastic"}],
        "location": "Near the community hall",
        "latitude": 6.4436,
        "longitude": 100.2700,
        "location_address": "Near the community hall, Arau, Perlis",
        "location_street": "Jalan Arau",
        "location_city": "Arau",
        "location_state": "Perlis",
        "location_postcode": "02600",
        "location_country": "Malaysia",
        "location_source": "map",
        "site_notes": "Accessible from the main road.",
    }


def create_florence_draft(tmp_path: Path) -> str:
    original = tmp_path / "florence-original.jpg"
    preview = tmp_path / "florence-preview.jpg"
    original.write_bytes(b"florence original")
    preview.write_bytes(b"florence preview")
    detections = [
        {"id": "det-0", "label": "plastic bottle", "name": "plastic_bottle",
         "display_name": "Plastic Bottle", "suggested_category": "Recyclable Waste",
         "material": "Plastic", "review_status": "likely_waste",
         "bounding_box": {"x1": 1, "y1": 2, "x2": 50, "y2": 80}},
        {"id": "det-1", "label": "tree", "name": "tree", "display_name": "Tree",
         "suggested_category": None, "material": "Unknown", "review_status": "background",
         "bounding_box": {"x1": 60, "y1": 2, "x2": 100, "y2": 100}},
        {"id": "det-2", "label": "bottle cap", "name": "bottle_cap",
         "display_name": "Bottle Cap", "suggested_category": None,
         "material": "Unknown", "review_status": "needs_confirmation",
         "bounding_box": {"x1": 2, "y1": 3, "x2": 10, "y2": 12}},
    ]
    return report_repository.create_analysis_draft(
        original_image_path=original, annotated_image_path=preview,
        detection={"provider": "florence2", "model_id": "microsoft/Florence-2-base",
                   "model_revision": "pinned", "model_detections": detections,
                   "raw_detections": detections, "detections": [],
                   "analysis": {"mode": "florence2", "provider": "florence2",
                                "model_id": "microsoft/Florence-2-base",
                                "model_revision": "pinned", "categories_detected": []}},
        report=None, user_id=MEMBER_USER["id"],
    )


def test_florence_review_persists_raw_corrections_and_mixed_final_items(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    draft_id = create_florence_draft(tmp_path)
    payload = submission_payload(draft_id)
    payload.update(rule_version="1.0.0", category="Hazardous Waste",
                   confirmed_items=[
                       {"review_id": "det-0", "name": "Plastic Bottle", "material": "Plastic",
                        "category": "Recyclable Waste"},
                       {"review_id": "manual-battery", "name": "Battery", "material": "Unknown",
                        "category": "Hazardous Waste"},
                   ],
                   reviewed_detections=[
                       {"id": "det-0", "source_detection_id": "det-0", "disposition": "waste",
                        "corrected_label": "Plastic Bottle", "material": "Plastic",
                        "category": "Recyclable Waste"},
                       {"id": "det-1", "source_detection_id": "det-1", "disposition": "removed",
                        "corrected_label": "tree", "material": "Unknown"},
                       {"id": "det-2", "source_detection_id": "det-2",
                        "disposition": "attached_component", "corrected_label": "Bottle Cap",
                        "material": "Unknown", "component_relation": "attached"},
                       {"id": "manual-battery", "source_detection_id": None,
                        "disposition": "waste", "corrected_label": "Battery",
                        "material": "Unknown", "category": "Hazardous Waste"},
                   ])
    response = client.post("/api/reports", json=payload)
    assert response.status_code == 201, response.text
    with sqlite3.connect(tmp_path / "reports.db") as database:
        database.row_factory = sqlite3.Row
        saved = database.execute("SELECT * FROM reports WHERE analysis_id = ?", (draft_id,)).fetchone()
        draft = database.execute("SELECT detection_json FROM analysis_drafts WHERE id = ?", (draft_id,)).fetchone()
    assert json.loads(draft["detection_json"])["model_detections"] == json.loads(draft["detection_json"])["raw_detections"]
    assert saved["category"] == "Hazardous Waste"
    assert json.loads(saved["final_categories_json"]) == ["Recyclable Waste", "Hazardous Waste"]
    confirmation = json.loads(saved["confirmed_ai_result_json"])
    assert [entry["disposition"] for entry in confirmation["user_corrections"]] == ["waste", "removed", "attached_component", "waste"]
    assert [entry["review_id"] for entry in confirmation["final_confirmed_items"]] == ["det-0", "manual-battery"]
    assert len(confirmation["applied_classification_rules"]) == 2


def test_florence_review_rejects_unresolved_or_unmatched_detections(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    draft_id = create_florence_draft(tmp_path)
    payload = submission_payload(draft_id)
    payload["rule_version"] = "1.0.0"
    payload["confirmed_items"][0]["review_id"] = "det-0"
    payload["reviewed_detections"] = [
        {"id": "det-0", "source_detection_id": "det-0", "disposition": "waste",
         "corrected_label": "Plastic Bottle", "material": "Plastic", "category": "Recyclable Waste"},
        {"id": "det-1", "source_detection_id": "det-1", "disposition": "background",
         "corrected_label": "tree", "material": "Unknown"},
    ]
    response = client.post("/api/reports", json=payload)
    assert response.status_code == 422
    assert "Every model detection" in response.json()["detail"]


def test_manual_review_keeps_added_item_and_rule_provenance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(reports_api, "UPLOAD_DIR", tmp_path / "uploads")
    payload = submission_payload(None)
    payload.update(rule_version="1.0.0",
                   confirmed_items=[{"review_id": "manual-1", "name": "Plastic Bottle",
                                     "category": "Recyclable Waste", "material": "Plastic"}],
                   reviewed_detections=[{"id": "manual-1", "source_detection_id": None,
                                         "disposition": "waste", "corrected_label": "Plastic Bottle",
                                         "category": "Recyclable Waste", "material": "Plastic"}])
    response = client.post("/api/reports/with-image", data={"payload": json.dumps(payload)},
                           files={"image": ("photo.png", VALID_PNG, "image/png")})
    assert response.status_code == 201, response.text
    with sqlite3.connect(tmp_path / "reports.db") as database:
        saved = database.execute("SELECT confirmed_ai_result_json FROM reports").fetchone()
    result = json.loads(saved[0])
    assert result["user_corrections"][0]["source_detection_id"] is None
    assert result["final_confirmed_items"][0]["source_detection_ids"] == []
    assert result["applied_classification_rules"][0]["rule_id"]


def test_detached_cap_is_a_separate_item_only_after_explicit_confirmation() -> None:
    draft = json.dumps({"provider": "florence2", "raw_detections": [
        {"id": "cap-1", "label": "bottle cap"},
    ]})
    confirmed = {"review_id": "cap-1", "name": "Bottle Cap",
                 "category": "Recyclable Waste", "material": "Plastic", "quantity": 1}
    review = {"id": "cap-1", "source_detection_id": "cap-1",
              "disposition": "waste", "corrected_label": "Bottle Cap",
              "category": "Recyclable Waste", "material": "Plastic", "quantity": 1}
    with pytest.raises(report_repository.ReviewValidationError, match="detached"):
        report_repository._build_review_confirmation(draft, {
            "confirmed_items": [confirmed], "reviewed_detections": [review],
        })
    review["component_relation"] = "detached"
    result = report_repository._build_review_confirmation(draft, {
        "confirmed_items": [confirmed], "reviewed_detections": [review],
    })
    assert result is not None
    assert result["final_confirmed_items"][0]["quantity"] == 1
    assert result["final_confirmed_items"][0]["source_detection_ids"] == ["cap-1"]


def test_report_draft_requires_complete_owned_review_and_never_submits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    draft_id = create_florence_draft(tmp_path)
    payload = {
        "analysis_id": draft_id,
        "confirmed_items": [{"review_id": "det-0", "name": "Plastic Bottle",
                             "material": "Plastic", "category": "Recyclable Waste"}],
        "reviewed_detections": [
            {"id": "det-0", "source_detection_id": "det-0", "disposition": "waste",
             "corrected_label": "Plastic Bottle", "material": "Plastic", "category": "Recyclable Waste"},
            {"id": "det-1", "source_detection_id": "det-1", "disposition": "background",
             "corrected_label": "tree", "material": "Unknown"},
            {"id": "det-2", "source_detection_id": "det-2", "disposition": "attached_component",
             "corrected_label": "Bottle Cap", "material": "Unknown", "component_relation": "attached"},
        ],
        "user_description": "Near a bench.",
        "confirmed_address": "Campus Gate",
    }
    observed = []
    monkeypatch.setattr(reports_api, "draft_confirmed_report", lambda items, **kwargs: (
        observed.append((items, kwargs)) or {"title": "Draft", "summary": "Description",
                                      "waste_identified": "Plastic Bottle", "recommended_action": "Review.",
                                      "environmental_concern": "May affect area.",
                                      "source": "template", "model_id": ""}))
    response = client.post("/api/reports/draft", json=payload)
    assert response.status_code == 200, response.text
    assert len(observed) == 1
    assert observed[0][1]["confirmed_address"] == "Campus Gate"
    with sqlite3.connect(tmp_path / "reports.db") as database:
        assert database.execute("SELECT COUNT(*) FROM reports").fetchone()[0] == 0
    payload["reviewed_detections"].pop()
    assert client.post("/api/reports/draft", json=payload).status_code == 422
    assert len(observed) == 1


def test_repeated_ai_analysis_drafts_never_create_reward_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)

    first_draft = create_draft(tmp_path)
    second_draft = create_draft(tmp_path)

    assert first_draft != second_draft
    with sqlite3.connect(report_repository.DATABASE_PATH) as database:
        reward_count = database.execute(
            "SELECT COUNT(*) FROM reward_events"
        ).fetchone()[0]
        report_count = database.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        stored_draft_report = database.execute(
            "SELECT ai_report_json FROM analysis_drafts WHERE id = ?",
            (first_draft,),
        ).fetchone()[0]
    assert reward_count == 0
    assert report_count == 0
    assert json.loads(stored_draft_report) == GENERATED_REPORT


def test_temporary_draft_assets_are_bound_to_their_owner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    create_draft(tmp_path)
    original = tmp_path / "upload.jpg"

    assert report_repository.analysis_draft_asset_belongs_to_user(
        MEMBER_USER["id"],
        original,
    )
    assert not report_repository.analysis_draft_asset_belongs_to_user(
        "different-user",
        original,
    )


def test_member_submission_persists_reviewed_report_and_images(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    draft_id = create_draft(tmp_path)
    payload = submission_payload(draft_id)
    payload["detections"] = [{"class_name": "user_modified_detection"}]
    payload["final_categories"] = ["Bulky Waste"]

    response = client.post("/api/reports", json=payload)

    assert response.status_code == 201
    result = response.json()
    assert result["reference"].startswith("SCA-")
    assert result["status"] == "submitted"
    assert result["original_image"].startswith("/api/reports/files/")
    assert result["annotated_image"].startswith("/api/reports/files/")

    with sqlite3.connect(report_repository.DATABASE_PATH) as database:
        database.row_factory = sqlite3.Row
        report = database.execute("SELECT * FROM reports").fetchone()
        draft = database.execute(
            "SELECT consumed_at, detection_json FROM analysis_drafts WHERE id = ?",
            (draft_id,),
        ).fetchone()
        detections = database.execute(
            """
            SELECT * FROM waste_detections
            WHERE report_id = ?
            ORDER BY class_name
            """,
            (report["id"],),
        ).fetchall()
        report_columns = {
            row[1] for row in database.execute("PRAGMA table_info(reports)")
        }

    assert report is not None
    assert report["guest_name"] is None
    assert report["user_id"] == MEMBER_USER["id"]
    assert report["title"] == "Reviewed waste report"
    assert report["summary"] == "The user-edited final summary."
    assert report["waste_identified"] == "One plastic bottle."
    assert report["recommended_action"] == "Collect and recycle it."
    assert report["environmental_concern"] == "It may contribute to litter."
    assert json.loads(report["final_categories_json"]) == ["Recyclable Waste"]
    ai_analysis = json.loads(report["ai_analysis_json"])
    assert ai_analysis["mode"] == "hybrid"
    assert ai_analysis["scene_description"] == "Two recyclable items are visible."
    assert "grouped_objects" not in ai_analysis
    assert report["latitude"] == pytest.approx(6.4436)
    assert report["longitude"] == pytest.approx(100.2700)
    assert report["location_city"] == "Arau"
    assert report["location_source"] == "map"
    assert report["status"] == "submitted"
    assert json.loads(report["confirmed_ai_result_json"])["items"] == payload["confirmed_items"]
    assert draft["consumed_at"] is not None
    assert json.loads(draft["detection_json"])["analysis"]["categories_detected"] == ["Recyclable Waste", "Bulky Waste"]
    assert "detection_json" not in report_columns
    assert {
        "latitude",
        "longitude",
        "location_address",
        "location_source",
    }.issubset(report_columns)
    assert len(detections) == 3
    assert detections[0]["class_name"] == "mattress"
    assert detections[0]["source"] == "vlm"
    assert detections[0]["confidence"] is None
    assert detections[0]["x1"] is None
    assert detections[0]["y1"] is None
    assert detections[0]["x2"] is None
    assert detections[0]["y2"] is None
    assert detections[1]["class_name"] == "metal_can"
    assert detections[1]["display_name"] == "Metal Can"
    assert detections[1]["waste_category"] == "Recyclable Waste"
    assert detections[1]["material"] == "Metal"
    assert detections[1]["confidence"] == pytest.approx(0.84)
    assert detections[1]["x1"] == pytest.approx(250.0)
    assert detections[1]["y1"] == pytest.approx(40.0)
    assert detections[1]["x2"] == pytest.approx(310.0)
    assert detections[1]["y2"] == pytest.approx(160.0)
    assert detections[1]["source"] == "yolo"
    assert detections[1]["created_at"] == report["created_at"]
    assert detections[2]["report_id"] == report["id"]
    assert draft["consumed_at"] is not None
    assert len(list((tmp_path / "assets" / result["id"]).iterdir())) == 2


def test_manual_report_location_persists_and_coordinate_fallback_requires_description(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    payload = submission_payload(create_draft(tmp_path))
    payload.update(latitude=-6.2, longitude=106.8, location_address="Behind the library",
                   location_address_source="manual", site_notes="Near the bins")
    response = client.post("/api/reports", json=payload)
    assert response.status_code == 201
    stored = report_repository.get_report(response.json()["id"])
    assert stored is not None
    assert stored["latitude"] == -6.2
    assert stored["longitude"] == 106.8
    assert stored["location_address"] == "Behind the library"
    assert stored["location_address_source"] == "manual"
    assert stored["site_notes"] == "Near the bins"

    fallback = submission_payload(create_draft(tmp_path))
    fallback.update(location_address_source="coordinates", site_notes="")
    assert client.post("/api/reports", json=fallback).status_code == 422
    fallback["site_notes"] = "Beside the loading bay"
    assert client.post("/api/reports", json=fallback).status_code == 201


def test_mixed_items_route_to_non_recyclable_and_submission_awards_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    payload = submission_payload(create_draft(tmp_path))
    payload["category"] = "Non-Recyclable Waste"
    payload["confirmed_items"].append({
        "name": "Food Wrapper", "category": "Non-Recyclable Waste", "material": "client value",
    })
    response = client.post("/api/reports", json=payload)
    assert response.status_code == 201
    assert response.json()["status"] == "submitted"
    with sqlite3.connect(report_repository.DATABASE_PATH) as database:
        category, confirmed = database.execute(
            "SELECT category, confirmed_ai_result_json FROM reports WHERE id = ?",
            (response.json()["id"],),
        ).fetchone()
        assert database.execute("SELECT COUNT(*) FROM reward_events").fetchone()[0] == 0
    assert category == "Non-Recyclable Waste"
    assert json.loads(confirmed)["items"][1]["material"] == "Mixed Packaging Material"


def test_recyclable_category_cannot_hide_non_recyclable_item(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    payload = submission_payload(create_draft(tmp_path))
    payload["confirmed_items"].append({
        "name": "Food Wrapper", "category": "Non-Recyclable Waste", "material": "Mixed Packaging Material",
    })
    assert client.post("/api/reports", json=payload).status_code == 422
    payload["confirmed_items"][1]["category"] = "Recyclable Waste"
    assert client.post("/api/reports", json=payload).status_code == 422


def test_bulky_item_routes_mixed_photo_to_campus_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    payload = submission_payload(create_draft(tmp_path))
    payload["category"] = "Bulky Waste"
    payload["confirmed_items"].append({
        "name": "Mattress", "category": "Bulky Waste", "material": "client value",
    })
    response = client.post("/api/reports", json=payload)
    assert response.status_code == 201
    with sqlite3.connect(report_repository.DATABASE_PATH) as database:
        row = database.execute("SELECT category, confirmed_ai_result_json FROM reports").fetchone()
    assert row[0] == "Bulky Waste"
    assert json.loads(row[1])["items"][1]["category"] == "Bulky Waste"


def test_report_submission_accepts_valid_location_outside_former_campus_boundary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    assert client.post("/api/reports/campus-location/check", json={
        "latitude": 6.8, "longitude": 100.27,
    }).status_code == 404
    payload = submission_payload(create_draft(tmp_path))
    payload["latitude"] = 6.8
    response = client.post("/api/reports", json=payload)
    assert response.status_code == 201
    with sqlite3.connect(report_repository.DATABASE_PATH) as database:
        assert database.execute("SELECT latitude FROM reports").fetchone()[0] == 6.8


def test_report_submission_does_not_require_boundary_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    response = client.post("/api/reports", json=submission_payload(create_draft(tmp_path)))
    assert response.status_code == 201


def test_unknown_item_can_be_confirmed_for_reporting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    payload = submission_payload(create_draft(tmp_path))
    payload["confirmed_items"] = [{
        "name": "Unidentified fragment", "category": "Non-Recyclable Waste", "material": "Unknown",
    }]
    payload["category"] = "Non-Recyclable Waste"
    response = client.post("/api/reports", json=payload)
    assert response.status_code == 201
    assert response.json()["status"] == "submitted"


def test_member_submission_stores_user_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    draft_id = create_draft(tmp_path)
    payload = submission_payload(draft_id)
    payload.update(
        reporter_role="user",
        user_id="usr-204",
        guest_name=None,
        guest_email=None,
    )

    response = client.post("/api/reports", json=payload)

    assert response.status_code == 201
    with sqlite3.connect(report_repository.DATABASE_PATH) as database:
        row = database.execute(
            "SELECT user_id, guest_name, guest_email FROM reports"
        ).fetchone()
        reward_count = database.execute(
            "SELECT COUNT(*) FROM reward_events"
        ).fetchone()[0]
    assert row == ("usr-204", None, None)
    assert reward_count == 0


def test_member_reward_is_created_once_after_admin_validation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    draft_id = create_draft(tmp_path)
    payload = submission_payload(draft_id)
    payload.update(
        reporter_role="user",
        user_id="usr-204",
        guest_name=None,
        guest_email=None,
    )
    submission = client.post("/api/reports", json=payload)
    report_id = submission.json()["id"]

    # Re-analysis, another generated draft, and reopening the report are read or
    # draft operations and must not create rewards.
    create_draft(tmp_path)
    assert client.get(f"/api/reports/{report_id}").status_code == 200
    assert client.get(f"/api/reports/{report_id}").status_code == 200
    with sqlite3.connect(report_repository.DATABASE_PATH) as database:
        assert database.execute(
            "SELECT COUNT(*) FROM reward_events"
        ).fetchone()[0] == 0

    first_validation = client.post(
        f"/api/reports/{report_id}/validation",
        json={"validation_status": "valid"},
    )
    retried_validation = client.post(
        f"/api/reports/{report_id}/validation",
        json={"validation_status": "valid"},
    )

    assert first_validation.status_code == 200
    assert first_validation.json() == {
        "report_id": report_id,
        "validation_status": "valid",
        "status": "in_progress",
        "reward_awarded": True,
        "reward_points": 2,
    }
    assert retried_validation.status_code == 200
    assert retried_validation.json()["reward_awarded"] is False
    assert retried_validation.json()["reward_points"] == 0
    reopened = client.get(f"/api/reports/{report_id}")
    assert reopened.status_code == 200
    assert reopened.json()["reward_points"] == 2

    with sqlite3.connect(report_repository.DATABASE_PATH) as database:
        report = database.execute(
            "SELECT validation_status, status, validated_at FROM reports"
        ).fetchone()
        rewards = database.execute(
            "SELECT report_id, user_id, points, reason FROM reward_events"
        ).fetchall()

    assert report[0:2] == ("valid", "in_progress")
    assert report[2] is not None
    assert rewards == [
        (report_id, "usr-204", 2, "validated_report"),
    ]


def test_invalid_report_cannot_generate_a_reward_or_be_revalidated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    payload = submission_payload(create_draft(tmp_path))
    payload.update(
        reporter_role="user",
        user_id="usr-204",
        guest_name=None,
        guest_email=None,
    )
    submission = client.post("/api/reports", json=payload)
    report_id = submission.json()["id"]

    invalid = client.post(
        f"/api/reports/{report_id}/validation",
        json={"validation_status": "invalid"},
    )
    reversal = client.post(
        f"/api/reports/{report_id}/validation",
        json={"validation_status": "valid"},
    )

    assert invalid.status_code == 200
    assert invalid.json()["reward_awarded"] is False
    assert invalid.json()["status"] == "completed"
    assert reversal.status_code == 409
    with sqlite3.connect(report_repository.DATABASE_PATH) as database:
        reward_count = database.execute(
            "SELECT COUNT(*) FROM reward_events"
        ).fetchone()[0]
    assert reward_count == 0


def test_analysis_draft_cannot_be_submitted_twice(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    draft_id = create_draft(tmp_path)
    payload = submission_payload(draft_id)

    assert client.post("/api/reports", json=payload).status_code == 201
    response = client.post("/api/reports", json=payload)

    assert response.status_code == 409
    assert response.json()["detail"] == "This analysis draft has already been submitted."


def test_report_without_photo_or_analysis_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    payload = submission_payload(None)
    payload["waste_identified"] = ""
    payload["recommended_action"] = ""
    payload["environmental_concern"] = ""

    response = client.post("/api/reports", json=payload)

    assert response.status_code == 422
    assert "photo" in response.json()["detail"].lower()


def test_member_can_submit_uploaded_image_without_ai(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(reports_api, "UPLOAD_DIR", upload_dir)
    payload = submission_payload(None)
    payload["waste_identified"] = ""
    payload["recommended_action"] = ""
    payload["environmental_concern"] = ""

    response = client.post(
        "/api/reports/with-image",
        data={"payload": json.dumps(payload)},
        files={"image": ("guest-evidence.png", VALID_PNG, "image/png")},
    )

    assert response.status_code == 201
    result = response.json()
    assert result["original_image"].startswith("/api/reports/files/")
    assert result["annotated_image"] == ""
    assert list(upload_dir.iterdir()) == []
    stored_images = list((tmp_path / "assets" / result["id"]).iterdir())
    assert len(stored_images) == 1
    assert stored_images[0].name == "original.png"


def test_member_submission_succeeds_when_temporary_cleanup_fails(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(reports_api, "UPLOAD_DIR", tmp_path / "uploads")
    payload = submission_payload(None)
    payload.update(
        waste_identified="",
        recommended_action="",
        environmental_concern="",
    )

    def fail_cleanup(_path: Path, *, missing_ok: bool = False) -> None:
        raise OSError("cleanup unavailable")

    monkeypatch.setattr(Path, "unlink", fail_cleanup)

    response = client.post(
        "/api/reports/with-image",
        data={"payload": json.dumps(payload)},
        files={"image": ("guest-evidence.png", VALID_PNG, "image/png")},
    )

    assert response.status_code == 201
    assert "report_upload_cleanup_failed" in caplog.text


def test_admin_report_reads_include_saved_ai_detections(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    draft_id = create_draft(tmp_path)
    submission = client.post("/api/reports", json=submission_payload(draft_id))
    report_id = submission.json()["id"]

    list_response = client.get("/api/reports")
    detail_response = client.get(f"/api/reports/{report_id}")

    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == report_id
    assert list_response.json()[0]["confidence"] == 90
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["reference"] == submission.json()["reference"]
    assert detail["generated_report"] == GENERATED_REPORT
    assert detail["reward_points"] == 0
    assert detail["summary"] == "The user-edited final summary."
    assert detail["final_categories"] == ["Recyclable Waste"]
    assert detail["confirmed_results"]["items"] == submission_payload(draft_id)["confirmed_items"]
    assert detail["ai_analysis"]["mode"] == "hybrid"
    assert detail["latitude"] == pytest.approx(6.4436)
    assert detail["longitude"] == pytest.approx(100.2700)
    assert detail["location_address"] == "Near the community hall, Arau, Perlis"
    assert detail["location_source"] == "map"
    assert detail["original_image"].startswith("/api/reports/files/")
    assert detail["annotated_image"].startswith("/api/reports/files/")
    assert len(detail["detections"]) == 3
    assert detail["detections"][0]["class_name"] == "plastic_bottle"
    assert detail["detections"][0]["x1"] == pytest.approx(10.0)
    assert detail["detections"][0]["source"] == "yolo"
    assert detail["detections"][2]["class_name"] == "mattress"
    assert detail["detections"][2]["confidence"] is None
    assert detail["detections"][2]["x1"] is None
    assert detail["detections"][2]["source"] == "vlm"

    image_response = client.get(detail["annotated_image"])
    assert image_response.status_code == 200
    assert image_response.headers["x-content-type-options"] == "nosniff"
    assert image_response.headers["cache-control"] == "private, no-store"


def test_admin_report_handles_historical_row_without_coordinates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    submission = client.post("/api/reports", json=submission_payload(create_draft(tmp_path)))
    report_id = submission.json()["id"]
    with sqlite3.connect(report_repository.DATABASE_PATH) as database:
        database.execute(
            """
            UPDATE reports
            SET latitude = NULL, longitude = NULL, location_source = NULL
            WHERE id = ?
            """,
            (report_id,),
        )

    response = client.get(f"/api/reports/{report_id}")

    assert response.status_code == 200
    assert response.json()["latitude"] is None
    assert response.json()["longitude"] is None
    assert response.json()["location_source"] is None


def test_guest_submission_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    payload = submission_payload(create_draft(tmp_path))
    payload.update(reporter_role="guest", user_id=None, guest_name="Test Reporter", guest_email="reporter@example.com")

    response = client.post("/api/reports", json=payload)

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("field", "value"),
    [("latitude", 90.1), ("latitude", -90.1), ("longitude", 180.1)],
)
def test_report_submission_rejects_invalid_coordinates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    field: str,
    value: float,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    payload = submission_payload(None)
    payload[field] = value

    response = client.post("/api/reports", json=payload)

    assert response.status_code == 422


def test_ai_draft_cannot_be_submitted_as_guest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    draft_id = create_draft(tmp_path)
    payload = submission_payload(draft_id)
    payload.update(
        reporter_role="guest",
        user_id=None,
        guest_name="Test Reporter",
        guest_email="reporter@example.com",
    )

    response = client.post("/api/reports", json=payload)

    assert response.status_code == 403


def test_admin_report_routes_reject_non_admin_users() -> None:
    app.dependency_overrides.pop(require_admin_user, None)

    response = client.get("/api/reports")

    assert response.status_code == 403


def test_database_initialization_migrates_legacy_detection_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    legacy_detection = json.dumps(
        {
            "total_objects": len(DETECTIONS),
            "counts": {"plastic_bottle": 1, "metal_can": 1},
            "detections": DETECTIONS,
        }
    )
    with sqlite3.connect(report_repository.DATABASE_PATH) as database:
        database.execute(
            """
            CREATE TABLE reports (
                id TEXT PRIMARY KEY,
                detection_json TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        database.execute(
            "INSERT INTO reports (id, detection_json, created_at) VALUES (?, ?, ?)",
            ("legacy-report", legacy_detection, "2026-09-24T00:00:00+00:00"),
        )

    report_repository.initialize_database()
    report_repository.initialize_database()

    with sqlite3.connect(report_repository.DATABASE_PATH) as database:
        legacy_json = database.execute(
            "SELECT detection_json FROM reports WHERE id = 'legacy-report'"
        ).fetchone()[0]
        detections = database.execute(
            """
            SELECT report_id, class_name, created_at
            FROM waste_detections
            WHERE report_id = 'legacy-report'
            ORDER BY class_name
            """
        ).fetchall()

    assert legacy_json is None
    assert detections == [
        ("legacy-report", "metal_can", "2026-09-24T00:00:00+00:00"),
        ("legacy-report", "plastic_bottle", "2026-09-24T00:00:00+00:00"),
    ]


def test_database_initialization_allows_vlm_detection_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    response = client.post("/api/reports", json=submission_payload(create_draft(tmp_path)))
    report_id = response.json()["id"]

    with sqlite3.connect(report_repository.DATABASE_PATH) as database:
        database.execute("DROP INDEX idx_waste_detections_report_id")
        database.execute("DROP TABLE waste_detections")
        database.execute(
            """
            CREATE TABLE waste_detections (
                id TEXT PRIMARY KEY,
                report_id TEXT NOT NULL,
                class_name TEXT NOT NULL,
                display_name TEXT NOT NULL,
                waste_category TEXT NOT NULL,
                material TEXT NOT NULL,
                confidence REAL NOT NULL,
                x1 REAL NOT NULL,
                y1 REAL NOT NULL,
                x2 REAL NOT NULL,
                y2 REAL NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        database.execute(
            """
            INSERT INTO waste_detections VALUES (
                'old-detection', ?, 'plastic_bottle', 'Plastic Bottle',
                'Recyclable Waste', 'Plastic', 0.9, 1, 2, 3, 4,
                '2026-10-06T00:00:00+00:00'
            )
            """,
            (report_id,),
        )

    report_repository.initialize_database()

    with sqlite3.connect(report_repository.DATABASE_PATH) as database:
        database.row_factory = sqlite3.Row
        columns = {
            row["name"]: row
            for row in database.execute("PRAGMA table_info(waste_detections)")
        }
        migrated = database.execute(
            "SELECT * FROM waste_detections WHERE id = 'old-detection'"
        ).fetchone()

    assert columns["confidence"]["notnull"] == 0
    assert columns["x1"]["notnull"] == 0
    assert "source" in columns
    assert migrated["source"] == "yolo"
    assert migrated["confidence"] == pytest.approx(0.9)
