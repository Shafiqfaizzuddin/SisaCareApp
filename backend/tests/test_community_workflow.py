"""Repository checks for the additive municipal workflow without a live database."""

import sqlite3
from types import SimpleNamespace

import pytest

from app.repositories import reports


@pytest.fixture
def community_db(monkeypatch, tmp_path):
    database_path = tmp_path / "reports.db"
    monkeypatch.setattr(reports, "DATABASE_PATH", database_path)
    monkeypatch.setattr(reports, "REPORT_ASSETS_DIR", tmp_path / "assets")
    reports.initialize_database()
    with sqlite3.connect(database_path) as database:
        database.execute(
            """INSERT INTO reports (id, reference, reporter_role, user_id, title, summary,
               category, location, status, validation_status, created_at, updated_at)
               VALUES ('report-1', 'SCA-1', 'user', 'resident-1', 'Waste', 'Waste found',
               'Hazardous Waste', 'Community Hall', 'submitted', 'pending', '2026-10-18', '2026-10-18')"""
        )
    return database_path


def test_verify_assign_resolve_records_audit_without_rewards(community_db):
    verified = reports.validate_report("report-1", "valid", "admin-1")
    assert verified["status"] == "verified"
    assert verified["reward_points"] == 0
    assigned = reports.transition_report("report-1", "assign", "admin-1", assigned_team="Team A")
    assert assigned["status"] == "in_progress"
    resolved = reports.transition_report("report-1", "resolve", "admin-1", resolution_details="Collected by Team A")
    assert resolved["status"] == "resolved"
    with sqlite3.connect(community_db) as database:
        statuses = [row[0] for row in database.execute(
            "SELECT new_status FROM report_status_events WHERE report_id = 'report-1' ORDER BY rowid"
        )]
        assert statuses == ["verified", "in_progress", "resolved"]
        assert database.execute("SELECT COUNT(*) FROM reward_events").fetchone()[0] == 0


def test_rejection_requires_reason_and_preserves_submitted_record(community_db):
    with pytest.raises(ValueError, match="reason"):
        reports.validate_report("report-1", "invalid", "admin-1")
    rejected = reports.validate_report("report-1", "invalid", "admin-1", "Duplicate report")
    assert rejected["status"] == "rejected"
    with pytest.raises(reports.ValidationAlreadyDecidedError):
        reports.transition_report("report-1", "assign", "admin-1", assigned_team="Team A")
    with sqlite3.connect(community_db) as database:
        assert database.execute("SELECT rejection_reason FROM reports WHERE id = 'report-1'").fetchone()[0] == "Duplicate report"


def test_old_recycling_points_are_private_until_reviewed(community_db):
    from app.api.recycling import _list_points
    with sqlite3.connect(community_db) as database:
        database.execute(
            """INSERT INTO recycling_points (id, name, latitude, longitude, accepted_materials_json,
               active, data_origin, created_at, updated_at) VALUES
               ('station-1', 'Historical station', 6.4, 100.2, '["Plastic"]', 1, 'production', '2026', '2026')"""
        )
    assert _list_points(active_only=True) == []
    with sqlite3.connect(community_db) as database:
        database.execute("UPDATE recycling_points SET public_verified = 1 WHERE id = 'station-1'")
    assert [point["id"] for point in _list_points(active_only=True)] == ["station-1"]


def test_resident_tracking_is_owner_scoped(community_db):
    assert reports.get_own_report_tracking("report-1", "another-resident") is None
    own = reports.get_own_report_tracking("report-1", "resident-1")
    assert own is not None
    assert own["reference"] == "SCA-1"
    assert own["status"] == "submitted"


def test_browser_session_idle_absolute_and_explicit_revocation(monkeypatch, tmp_path):
    from app.repositories import browser_sessions
    settings = SimpleNamespace(database_path=tmp_path / "sessions.db", session_idle_seconds=60,
                               session_absolute_seconds=180)
    monkeypatch.setattr(browser_sessions, "get_settings", lambda: settings)
    clock = {"now": 1000}
    monkeypatch.setattr(browser_sessions.time, "time", lambda: clock["now"])
    user = {"id": "resident-1", "role": "user"}
    token = browser_sessions.create(user)
    assert browser_sessions.read(token) == user
    clock["now"] = 1059
    assert browser_sessions.read(token) == user
    clock["now"] = 1120
    assert browser_sessions.read(token) is None
    token = browser_sessions.create(user)
    clock["now"] = 1170
    assert browser_sessions.read(token) == user
    clock["now"] = 1220
    assert browser_sessions.read(token) == user
    clock["now"] = 1270
    assert browser_sessions.read(token) == user
    clock["now"] = 1300
    assert browser_sessions.read(token) is None
    token = browser_sessions.create(user)
    browser_sessions.revoke(token)
    assert browser_sessions.read(token) is None
