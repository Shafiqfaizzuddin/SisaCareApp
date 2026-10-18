"""Community onboarding retires matric and E-Merit while retaining old audits."""

import sqlite3

import pytest
from fastapi import HTTPException

from app.api.identity import MatricSubmission, post_e_merit_eligibility, post_my_matric
from app.api.reports import ReportSubmission, _authorize_submission
from app.core.config import Settings
from app.repositories import identities


def test_community_identity_does_not_suggest_matric(monkeypatch, tmp_path):
    path = tmp_path / "identities.db"
    monkeypatch.setattr(identities, "get_settings", lambda: Settings(_env_file=None, database_path=path))
    created = identities.read_identity("resident-1", "123@student.uitm.edu.my", email_verified=True)
    assert created["matric_number"] is None
    with sqlite3.connect(path) as database:
        database.execute("UPDATE member_identities SET matric_number = 'historical-123' WHERE user_id = 'resident-1'")
    historical = identities.read_identity("resident-1", "123@student.uitm.edu.my", email_verified=True)
    assert historical["matric_number"] == "historical-123"


def test_new_matric_and_emerit_claims_are_retired():
    user = {"id": "resident-1", "role": "user", "email": "person@gmail.com"}
    matric_request = post_my_matric(MatricSubmission(matric_number="old-number"), user, None)
    with pytest.raises(HTTPException) as exc:
        matric_request.send(None)
    assert exc.value.status_code == 410
    merit_request = post_e_merit_eligibility(user)
    with pytest.raises(HTTPException) as exc:
        merit_request.send(None)
    assert exc.value.status_code == 410


def test_new_report_does_not_snapshot_student_or_staff_claim():
    submission = ReportSubmission(
        reporter_role="user", title="Waste", summary="Waste found", category="Non-Recyclable Waste",
        confirmed_items=[{"name": "General waste", "category": "Non-Recyclable Waste"}],
        location="Community Hall", latitude=6.4436, longitude=100.27, location_source="map",
    )
    for claim in ("student", "staff"):
        authorized = _authorize_submission(submission, {"id": "resident-1", "role": "user", "claimed_affiliation": claim})
        assert authorized["activity_affiliation"] == "unknown"
