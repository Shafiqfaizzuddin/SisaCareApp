from pathlib import Path
from uuid import uuid4
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.api.reports import ReportSubmission, _authorize_submission
from app.core.auth import require_admin_user, require_authenticated_user
from app.core.config import Settings
from app.main import app
from app.repositories import identities, reports


client = TestClient(app)
STUDENT = {"id": "student-1", "email": "2025516823@student.uitm.edu.my", "role": "user", "email_verified": True}
ADMIN = {"id": "admin-1", "email": "admin@uitm.edu.my", "role": "admin", "email_verified": True}


@pytest.fixture(autouse=True)
def database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    path = tmp_path / "sisacare.db"
    monkeypatch.setattr(identities, "get_settings", lambda: Settings(_env_file=None, database_path=path))
    monkeypatch.setattr(reports, "DATABASE_PATH", path)
    app.dependency_overrides[require_authenticated_user] = lambda: STUDENT
    yield
    app.dependency_overrides.clear()


def review(user_id: str, decision: str, reason: str | None = None) -> dict[str, object]:
    return identities.review_matric(
        user_id, "admin-1", decision, "prototype_manual",
        "Agreed student register checked for UiTM Arau", reason,
    )


def award_report(user_id: str, affiliation: str) -> None:
    now = "2026-01-01T00:00:00+00:00"
    report_id = uuid4().hex
    with reports._connect() as database:
        reports.initialize_database(database)
        database.execute(
            """INSERT INTO reports (id, reference, reporter_role, user_id, title, summary,
               category, location, status, validation_status, activity_affiliation,
               data_origin, created_at, updated_at)
               VALUES (?, ?, 'user', ?, 'Test', 'Test', 'household', 'Arau', 'processing',
               'pending', ?, 'production', ?, ?)""",
            (report_id, f"ref-{report_id}", user_id, affiliation, now, now),
        )
    reports.validate_report(report_id, "valid")


def test_student_submission_queue_rejection_resubmission_and_approval() -> None:
    initial = client.get("/api/identity/me")
    assert initial.status_code == 200
    assert initial.json()["matric_status"] == "not_submitted"
    assert initial.json()["matric_number"] == "2025516823"
    assert initial.headers["cache-control"] == "private, no-store"
    assert client.post("/api/identity/me/e-merit/eligibility").status_code == 409

    submitted = client.post("/api/identity/me/matric", json={"matric_number": "2025516823", "matric_status": "verified"})
    assert submitted.status_code == 200
    assert submitted.json()["matric_status"] == "pending"
    assert submitted.json()["matric_submitted_at"]
    award_report("student-1", "student")
    assert reports.get_member_dashboard("student-1")["points"] > 0
    assert client.get("/api/identity/admin/matric/pending").status_code == 403
    unauthorized_payload = {"decision": "verified", "verification_method": "prototype_manual",
                            "review_reference": "Agreed procedure", "procedure_confirmed": True}
    assert client.post("/api/identity/admin/matric/student-1/review", json=unauthorized_payload).status_code == 403

    app.dependency_overrides[require_admin_user] = lambda: ADMIN
    queue = client.get("/api/identity/admin/matric/pending")
    assert queue.status_code == 200
    assert queue.headers["cache-control"] == "private, no-store"
    assert queue.json()[0]["matric_number"] == "2025516823"
    assert queue.json()[0]["matric_submitted_email"] == STUDENT["email"]
    unconfirmed = client.post("/api/identity/admin/matric/student-1/review", json={**unauthorized_payload, "procedure_confirmed": False})
    assert unconfirmed.status_code == 422
    payload = {"decision": "rejected", "verification_method": "prototype_manual",
               "review_reference": "Agreed student register checked", "rejection_reason": "Record did not match",
               "procedure_confirmed": True}
    rejected = client.post("/api/identity/admin/matric/student-1/review", json=payload)
    assert rejected.status_code == 200
    del app.dependency_overrides[require_admin_user]
    rejected_identity = client.get("/api/identity/me").json()
    assert rejected_identity["matric_rejection_reason"] == "Record did not match"
    assert rejected_identity["matric_reviewed_by"] == "admin-1"
    assert rejected_identity["matric_reviewed_at"]
    assert rejected_identity["matric_verification_method"] == "prototype_manual"
    assert client.post("/api/identity/me/e-merit/eligibility").status_code == 409

    corrected = client.post("/api/identity/me/matric", json={"matric_number": "corrected-value"})
    assert corrected.json()["matric_status"] == "pending"
    assert corrected.json()["matric_source"] == "self_reported"
    assert corrected.json()["matric_rejection_reason"] is None
    review("student-1", "verified")
    assert client.get("/api/identity/me").json()["e_merit_identity_eligible"] is True


def test_duplicate_verified_matric_and_changed_number_requires_review() -> None:
    identities.submit_matric("student-1", STUDENT["email"], "2025516823")
    identities.submit_matric("student-2", "other@student.uitm.edu.my", "2025516823")
    review("student-1", "verified")
    with pytest.raises(ValueError, match="already assigned"):
        review("student-2", "verified")
    assert identities.submit_matric("student-2", "other@student.uitm.edu.my", "2025516823")["matric_status"] == "pending"
    changed = identities.submit_matric("student-1", STUDENT["email"], "different-number")
    assert changed["matric_status"] == "pending"
    assert changed["matric_source"] == "self_reported"
    assert changed["e_merit_identity_eligible"] is False
    assert client.post("/api/identity/me/e-merit/eligibility").status_code == 409


def test_staff_points_never_become_e_merit_eligible_after_profile_edit() -> None:
    identities.update_identity("student-1", STUDENT["email"], "staff", None)
    for _ in range(25):
        award_report("student-1", identities.activity_affiliation("student-1"))
    transitioned = identities.submit_matric("student-1", STUDENT["email"], "2025516823")
    assert transitioned["claimed_affiliation"] == "student"
    assert transitioned["matric_status"] == "pending"
    review("student-1", "verified")
    assert identities.read_identity("student-1", STUDENT["email"], email_verified=True)["e_merit_available_points"] == 0
    assert client.post("/api/identity/me/e-merit/eligibility").status_code == 409
    for _ in range(25):
        award_report("student-1", identities.activity_affiliation("student-1"))
    eligible = client.post("/api/identity/me/e-merit/eligibility")
    assert eligible.status_code == 201
    assert eligible.json()["status"] == "pending_approval"
    assert client.post("/api/identity/me/e-merit/eligibility").status_code == 409
    staff_again = identities.update_identity("student-1", STUDENT["email"], "staff", None)
    assert staff_again["e_merit_identity_eligible"] is False
    assert staff_again["matric_status"] == "not_submitted"
    with sqlite3.connect(identities.get_settings().database_path) as database:
        status = database.execute("SELECT status FROM e_merit_eligibility WHERE id = ?", (eligible.json()["id"],)).fetchone()[0]
    assert status == "cancelled_affiliation_change"
    assert client.post("/api/identity/me/e-merit/eligibility").status_code == 409


def test_report_uses_signup_claim_before_profile_is_opened() -> None:
    submission = ReportSubmission(
        reporter_role="user", title="Waste", summary="Waste found", category="Non-Recyclable Waste",
        confirmed_items=[{"name": "General waste", "category": "Non-Recyclable Waste"}],
        location="Arau", latitude=6.4436, longitude=100.27, location_source="map",
    )
    student = _authorize_submission(submission, {**STUDENT, "claimed_affiliation": "student"})
    assert student["activity_affiliation"] == "student"
    staff = _authorize_submission(submission, {**STUDENT, "claimed_affiliation": "staff"})
    assert staff["activity_affiliation"] == "staff"


def test_legacy_flag_without_review_is_queued_and_changing_verified_number_cancels_pending_e_merit() -> None:
    identities.read_identity("legacy", "legacy@student.uitm.edu.my", email_verified=True)
    path = identities.get_settings().database_path
    with sqlite3.connect(path) as database:
        database.execute(
            "UPDATE member_identities SET claimed_affiliation = 'student', verified_affiliation = 'student', matric_number = 'legacy-matric', matric_verified = 1 WHERE user_id = 'legacy'"
        )
    migrated = identities.read_identity("legacy", "legacy@student.uitm.edu.my", email_verified=True)
    assert migrated["matric_status"] == "pending"
    assert migrated["e_merit_identity_eligible"] is False
    review("legacy", "verified")
    for _ in range(25):
        award_report("legacy", "student")
    created = identities.create_e_merit_eligibility("legacy")
    changed = identities.submit_matric("legacy", "legacy@student.uitm.edu.my", "corrected")
    assert changed["matric_status"] == "pending"
    assert changed["e_merit_identity_eligible"] is False
    with sqlite3.connect(path) as database:
        status = database.execute("SELECT status FROM e_merit_eligibility WHERE id = ?", (created["id"],)).fetchone()[0]
    assert status == "cancelled_matric_change"


def test_converted_points_cannot_fund_another_eligibility_record() -> None:
    identities.submit_matric("student-1", STUDENT["email"], "2025516823")
    review("student-1", "verified")
    for _ in range(25):
        award_report("student-1", "student")
    first = identities.create_e_merit_eligibility("student-1")
    with sqlite3.connect(identities.get_settings().database_path) as database:
        database.execute(
            "UPDATE e_merit_eligibility SET status = 'converted' WHERE id = ?",
            (first["id"],),
        )
    assert identities.read_identity(
        "student-1", STUDENT["email"], email_verified=True,
    )["e_merit_available_points"] == 0
    with pytest.raises(ValueError, match="50 available"):
        identities.create_e_merit_eligibility("student-1")
