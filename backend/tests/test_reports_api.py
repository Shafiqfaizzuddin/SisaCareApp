import base64
import json
import sqlite3
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.api import reports as reports_api
from app.core.auth import get_optional_authenticated_user, require_admin_user
from app.repositories import reports as report_repository


client = TestClient(app)
MEMBER_USER = {
    "id": "usr-204",
    "email": "member@example.com",
    "role": "user",
}
ADMIN_USER = {
    "id": "admin-1",
    "email": "admin@example.com",
    "role": "admin",
}


@pytest.fixture(autouse=True)
def authenticated_api_users() -> None:
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
        "reporter_role": "user" if draft_id else "guest",
        "user_id": MEMBER_USER["id"] if draft_id else None,
        "guest_name": None if draft_id else "Test Reporter",
        "guest_email": None if draft_id else "reporter@example.com",
        "title": "Reviewed waste report",
        "summary": "The user-edited final summary.",
        "waste_identified": "One plastic bottle.",
        "recommended_action": "Collect and recycle it.",
        "environmental_concern": "It may contribute to litter.",
        "category": "recyclable",
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
    assert result["status"] == "processing"
    assert result["original_image"].startswith("/api/reports/files/")
    assert result["annotated_image"].startswith("/api/reports/files/")

    with sqlite3.connect(report_repository.DATABASE_PATH) as database:
        database.row_factory = sqlite3.Row
        report = database.execute("SELECT * FROM reports").fetchone()
        draft = database.execute(
            "SELECT consumed_at FROM analysis_drafts WHERE id = ?",
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
    assert json.loads(report["final_categories_json"]) == [
        "Recyclable Waste",
        "Bulky Waste",
    ]
    ai_analysis = json.loads(report["ai_analysis_json"])
    assert ai_analysis["mode"] == "hybrid"
    assert ai_analysis["scene_description"] == "Two recyclable items are visible."
    assert "grouped_objects" not in ai_analysis
    assert report["latitude"] == pytest.approx(6.4436)
    assert report["longitude"] == pytest.approx(100.2700)
    assert report["location_city"] == "Arau"
    assert report["location_source"] == "map"
    assert report["status"] == "processing"
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
        "reward_points": 40,
    }
    assert retried_validation.status_code == 200
    assert retried_validation.json()["reward_awarded"] is False
    assert retried_validation.json()["reward_points"] == 0
    reopened = client.get(f"/api/reports/{report_id}")
    assert reopened.status_code == 200
    assert reopened.json()["reward_points"] == 40

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
        (report_id, "usr-204", 40, "validated_report"),
    ]


def test_invalid_report_cannot_generate_a_reward_or_be_revalidated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    payload = submission_payload(None)
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


def test_non_ai_report_submission_remains_supported(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    payload = submission_payload(None)
    payload["waste_identified"] = ""
    payload["recommended_action"] = ""
    payload["environmental_concern"] = ""

    response = client.post("/api/reports", json=payload)

    assert response.status_code == 201
    result = response.json()
    assert result["original_image"] == ""
    assert result["annotated_image"] == ""
    with sqlite3.connect(report_repository.DATABASE_PATH) as database:
        detection_count = database.execute(
            "SELECT COUNT(*) FROM waste_detections"
        ).fetchone()[0]
    assert detection_count == 0


def test_guest_can_submit_uploaded_image_without_ai(
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


def test_guest_submission_succeeds_when_temporary_cleanup_fails(
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
    assert detail["final_categories"] == ["Recyclable Waste", "Bulky Waste"]
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
    submission = client.post("/api/reports", json=submission_payload(None))
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


def test_guest_submission_requires_guest_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_report_storage(monkeypatch, tmp_path)
    payload = submission_payload(None)
    payload["guest_name"] = ""

    response = client.post("/api/reports", json=payload)

    assert response.status_code == 422


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
    response = client.post("/api/reports", json=submission_payload(None))
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
