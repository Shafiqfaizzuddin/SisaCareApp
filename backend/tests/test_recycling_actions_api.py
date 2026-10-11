import io
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from app.api import recycling as recycling_api
from app.core.auth import get_optional_authenticated_user, require_admin_user
from app.core.config import Settings
from app.main import app
from app.repositories import identities, reports


client = TestClient(app)
STUDENT = {"id": "student-1", "email": "s@example.com", "role": "user", "email_verified": True,
           "google_sub": None, "has_google_provider": False, "claimed_affiliation": "student"}
OTHER = {**STUDENT, "id": "student-2"}
STAFF = {**STUDENT, "id": "staff-1", "claimed_affiliation": "staff"}
ADMIN = {**STUDENT, "id": "admin-1", "role": "admin"}


def photo_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (4, 4), "green").save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
def setup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(reports, "DATABASE_PATH", tmp_path / "actions.db")
    monkeypatch.setattr(reports, "REPORT_ASSETS_DIR", tmp_path / "assets")
    monkeypatch.setattr(identities, "get_settings", lambda: Settings(_env_file=None, database_path=tmp_path / "identities.db"))
    monkeypatch.setattr(recycling_api, "get_settings", lambda: SimpleNamespace(upload_dir=tmp_path / "uploads"))
    app.dependency_overrides[get_optional_authenticated_user] = lambda: STUDENT
    app.dependency_overrides[require_admin_user] = lambda: ADMIN
    with reports._connect() as database:
        reports.initialize_database(database)
        database.execute(
            """INSERT INTO recycling_points
               (id, name, latitude, longitude, accepted_materials_json, active, created_at, updated_at)
               VALUES ('point-1', 'Registered point', 6.4, 100.2, '["Plastic"]', 1, 'now', 'now')"""
        )
    yield tmp_path
    app.dependency_overrides.clear()


def draft(root: Path, owner: str = "student-1") -> str:
    original = root / f"original-{len(list(root.glob('original-*')))}.png"
    annotated = root / f"annotated-{original.stem}.png"
    original.write_bytes(photo_bytes())
    annotated.write_bytes(photo_bytes())
    return reports.create_analysis_draft(original_image_path=original, annotated_image_path=annotated,
        detection={"detections": []}, report=None, user_id=owner)


def payload(analysis_id: str, **changes: object) -> str:
    value = {"analysis_id": analysis_id, "recycling_point_id": "point-1",
             "confirmed_items": [{"name": "Plastic Bottle", "category": "Recyclable Waste", "material": "Plastic"}],
             "proof_location_source": "manual", "proof_location": "Near registered point"}
    value.update(changes)
    return json.dumps(value)


def submit(analysis_id: str, **changes: object):
    return client.post("/api/recycling/actions", data={"payload": payload(analysis_id, **changes)},
                       files={"proof": ("proof.png", photo_bytes(), "image/png")})


def test_requires_proof_and_enforces_draft_ownership_and_repeat(setup: Path) -> None:
    analysis_id = draft(setup)
    assert client.post("/api/recycling/actions", data={"payload": payload(analysis_id)}).status_code == 422
    foreign = draft(setup, owner="student-2")
    assert submit(foreign).status_code == 403
    response = submit(analysis_id)
    assert response.status_code == 201, response.text
    action = response.json()
    assert action["verification_status"] == "pending"
    assert action["proof_location_source"] == "manual"
    assert submit(analysis_id).status_code == 409
    assert client.get("/api/recycling/actions/me").json()[0]["id"] == action["id"]
    with reports._connect() as database:
        assert database.execute("SELECT COUNT(*) FROM reward_events").fetchone()[0] == 0
    app.dependency_overrides[get_optional_authenticated_user] = lambda: OTHER
    assert client.get(f"/api/recycling/actions/me/{action['id']}").status_code == 404
    assert client.get(action["proof_photo"]).status_code == 404


def test_upload_validation_and_point_match(setup: Path) -> None:
    analysis_id = draft(setup)
    assert client.post("/api/recycling/actions", data={"payload": payload(analysis_id)},
                       files={"proof": ("proof.txt", b"bad", "text/plain")}).status_code == 415
    assert client.post("/api/recycling/actions", data={"payload": payload(analysis_id)},
                       files={"proof": ("proof.png", b"bad", "image/png")}).status_code == 400
    assert client.post("/api/recycling/actions", data={"payload": payload(analysis_id)},
                       files={"proof": ("proof.png", b"x" * (10 * 1024 * 1024 + 1), "image/png")}).status_code == 413
    assert submit(analysis_id, proof_location="", proof_location_source="manual").status_code == 422
    assert submit(analysis_id, confirmed_items=[{"name": "Scrap Metal", "category": "Recyclable Waste", "material": "Metal"}]).status_code == 409
    with reports._connect() as database:
        database.execute("UPDATE recycling_points SET active = 0 WHERE id = 'point-1'")
    assert submit(analysis_id).status_code == 404


def test_recycling_proof_accepts_valid_gps_outside_former_campus_boundary(setup: Path) -> None:
    response = submit(draft(setup), proof_location_source="gps", proof_location=None,
                      proof_latitude=6.8, proof_longitude=100.3)
    assert response.status_code == 201, response.text
    assert response.json()["proof_latitude"] == 6.8


def test_admin_review_awards_once_and_freezes_evidence(setup: Path) -> None:
    action = submit(draft(setup)).json()
    action_id = action["id"]
    assert client.get(action["original_photo"]).status_code == 200
    assert client.get(action["proof_photo"]).status_code == 200
    queue = client.get("/api/recycling/admin/actions/pending")
    assert queue.status_code == 200
    assert queue.json()[0]["id"] == action_id
    reviewed = client.post(f"/api/recycling/admin/actions/{action_id}/review", json={"decision": "verified"})
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["reward_points"] == 5
    assert client.post(f"/api/recycling/admin/actions/{action_id}/review", json={"decision": "verified"}).status_code == 409
    with reports._connect() as database:
        assert database.execute("SELECT signed_amount FROM reward_events WHERE recycling_action_id = ?", (action_id,)).fetchone()[0] == 5
        with pytest.raises(Exception):
            database.execute("UPDATE recycling_actions SET proof_location = 'changed' WHERE id = ?", (action_id,))
    duplicate = submit(draft(setup)).json()
    assert client.post(f"/api/recycling/admin/actions/{duplicate['id']}/review", json={"decision": "verified"}).status_code == 409
    rejected = client.post(f"/api/recycling/admin/actions/{duplicate['id']}/review",
                           json={"decision": "rejected", "rejection_reason": "Duplicate original photo"})
    assert rejected.status_code == 200
    assert client.get(f"/api/recycling/actions/me/{duplicate['id']}").json()["rejection_reason"] == "Duplicate original photo"


def test_staff_award_is_not_emerit_eligible(setup: Path) -> None:
    app.dependency_overrides[get_optional_authenticated_user] = lambda: STAFF
    action = submit(draft(setup, owner="staff-1")).json()
    assert client.post(f"/api/recycling/admin/actions/{action['id']}/review", json={"decision": "verified"}).status_code == 200
    with reports._connect() as database:
        row = database.execute("SELECT activity_affiliation, e_merit_classification FROM reward_events").fetchone()
        assert tuple(row) == ("staff", "ineligible_staff")


def test_participant_cannot_review_action(setup: Path) -> None:
    action = submit(draft(setup)).json()
    del app.dependency_overrides[require_admin_user]
    response = client.post(f"/api/recycling/admin/actions/{action['id']}/review", json={"decision": "verified"})
    assert response.status_code == 403
    with reports._connect() as database:
        assert database.execute("SELECT COUNT(*) FROM reward_events").fetchone()[0] == 0


def test_same_original_photo_cannot_earn_report_and_recycling_rewards(setup: Path) -> None:
    action = submit(draft(setup)).json()
    assert client.post(f"/api/recycling/admin/actions/{action['id']}/review", json={"decision": "verified"}).status_code == 200
    report = reports.create_report({
        "analysis_id": draft(setup), "reporter_role": "user", "user_id": "student-1",
        "title": "Bottle", "summary": "Bottle at campus point", "waste_identified": "Plastic Bottle",
        "recommended_action": "Collect", "environmental_concern": "Litter",
        "category": "Recyclable Waste", "confirmed_items": [{"name": "Plastic Bottle", "category": "Recyclable Waste", "material": "Plastic"}],
        "location": "Campus", "latitude": 6.4, "longitude": 100.2,
        "location_source": "map", "activity_affiliation": "student",
    })
    decision = reports.validate_report(report["id"], "valid", "admin-1")
    assert decision["reward_awarded"] is False
    with reports._connect() as database:
        assert database.execute("SELECT COUNT(*) FROM reward_events").fetchone()[0] == 1
