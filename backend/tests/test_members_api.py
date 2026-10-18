from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.auth import require_authenticated_user
from app.main import app
from app.repositories import reports as report_repository


client = TestClient(app)
MEMBER_USER = {
    "id": "member-1",
    "email": "member@example.com",
    "role": "user",
}


def report_submission(user_id: str, index: int) -> dict[str, object]:
    return {
        "analysis_id": None,
        "reporter_role": "user",
        "user_id": user_id,
        "guest_name": None,
        "guest_email": None,
        "title": f"Report {index}",
        "summary": "Member-submitted waste report.",
        "waste_identified": "",
        "recommended_action": "",
        "environmental_concern": "",
        "category": "household",
        "location": f"Location {index}",
        "latitude": 6.4436,
        "longitude": 100.2700,
        "location_address": f"Location {index}",
        "location_street": None,
        "location_city": "Arau",
        "location_state": "Perlis",
        "location_postcode": None,
        "location_country": "Malaysia",
        "location_source": "map",
        "site_notes": "",
    }


@pytest.fixture(autouse=True)
def member_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(report_repository, "DATABASE_PATH", tmp_path / "reports.db")
    monkeypatch.setattr(report_repository, "REPORT_ASSETS_DIR", tmp_path / "assets")
    app.dependency_overrides[require_authenticated_user] = lambda: MEMBER_USER
    yield
    app.dependency_overrides.clear()


def test_member_dashboard_uses_owned_reports_without_new_rewards() -> None:
    report_repository.register_public_participant("member-1", "user")
    report_repository.register_public_participant("member-2", "user")
    pending = report_repository.create_report(report_submission("member-1", 1))
    validated = report_repository.create_report(report_submission("member-1", 2))
    report_repository.validate_report(validated["id"], "valid")

    for index in (1, 2):
        competitor = report_repository.create_report(
            report_submission("member-2", index)
        )
        report_repository.validate_report(competitor["id"], "valid")

    response = client.get("/api/members/me/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["points"] == 0
    assert payload["valid_reports"] == 0
    assert payload["rank"] is None
    assert {report["id"] for report in payload["reports"]} == {
        pending["id"],
        validated["id"],
    }
    assert all(report["location"].startswith("Location") for report in payload["reports"])


def test_member_without_rewards_is_unranked() -> None:
    report_repository.create_report(report_submission("member-1", 1))

    response = client.get("/api/members/me/dashboard")

    assert response.status_code == 200
    assert response.json()["points"] == 0
    assert response.json()["valid_reports"] == 0
    assert response.json()["rank"] is None


def test_admin_cannot_use_member_dashboard() -> None:
    app.dependency_overrides[require_authenticated_user] = lambda: {
        "id": "admin-1",
        "email": "admin@example.com",
        "role": "admin",
    }

    response = client.get("/api/members/me/dashboard")

    assert response.status_code == 403


def test_legacy_leaderboard_is_retired() -> None:
    report_repository.register_public_participant("member-1", "user", "member@uitm.edu.my")
    report_repository.register_public_participant("staff-1", "user", "staff@uitm.edu.my")
    report_repository.register_public_participant("demo-1", "user", "demo@example.com")
    report_repository.register_public_participant("admin-1", "admin", "admin@uitm.edu.my")
    for user_id in ("member-1", "staff-1", "demo-1", "admin-1"):
        item = report_repository.create_report(report_submission(user_id, 1))
        report_repository.validate_report(item["id"], "valid")
    with report_repository._connect() as database:
        report_repository.initialize_database(database)
        database.execute("""INSERT INTO reward_events
            (id, user_id, signed_amount, points, transaction_type, source_activity_type,
             source_activity_id, activity_key, reason, activity_affiliation, e_merit_classification,
             audit_reference, data_origin, created_at)
             VALUES ('conversion', 'member-1', -2, -2, 'adjustment', 'manual', 'conversion',
                     NULL, 'e_merit_conversion', 'student', 'ineligible_unknown', 'conversion-1',
                     'production', 'now')""")
    response = client.get("/api/members/leaderboard")
    assert response.status_code == 410
    assert "incentive policy" in response.json()["detail"]
