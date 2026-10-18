"""Historical recycling evidence remains reviewable; community proofs are retired."""

import sqlite3

import pytest
from fastapi import HTTPException

from app.api.recycling import submit_recycling_action
from app.repositories import recycling_actions, reports


@pytest.fixture
def old_action(monkeypatch, tmp_path):
    database_path = tmp_path / "reports.db"
    monkeypatch.setattr(reports, "DATABASE_PATH", database_path)
    monkeypatch.setattr(reports, "REPORT_ASSETS_DIR", tmp_path / "assets")
    reports.initialize_database()
    with sqlite3.connect(database_path) as database:
        database.execute(
            """INSERT INTO recycling_points (id, name, latitude, longitude,
               accepted_materials_json, active, created_at, updated_at)
               VALUES ('point-1', 'Historical station', 6.4, 100.2, '["Plastic"]', 1, '2026', '2026')"""
        )
        database.execute(
            """INSERT INTO recycling_actions (id, user_id, original_photo, confirmed_waste_json,
               recycling_point_id, proof_photo, proof_location, proof_location_source,
               activity_key, verification_status,
               data_origin, created_at, updated_at)
               VALUES ('action-1', 'resident-1', '/api/recycling/files/action-1/original.png', '{"items":[]}', 'point-1',
               '/api/recycling/files/action-1/proof.png', 'Historical station', 'manual',
               'old-activity', 'pending',
               'production', '2026', '2026')"""
        )
    return database_path


def test_historical_evidence_remains_owner_scoped(old_action):
    assert recycling_actions.get_action("action-1", "resident-1")["id"] == "action-1"
    with pytest.raises(recycling_actions.ActionNotFound):
        recycling_actions.get_action("action-1", "another-user")


def test_historical_review_is_final_and_issues_no_new_reward(old_action):
    reviewed = recycling_actions.review_action("action-1", "verified", "admin-1", None)
    assert reviewed["verification_status"] == "verified"
    assert reviewed["reward_points"] == 0
    with pytest.raises(recycling_actions.ActionConflict):
        recycling_actions.review_action("action-1", "verified", "admin-1", None)
    with sqlite3.connect(old_action) as database:
        assert database.execute("SELECT COUNT(*) FROM reward_events").fetchone()[0] == 0


def test_new_community_recycling_proof_is_retired():
    request = submit_recycling_action({"id": "resident-1", "role": "user"}, "{}", None)
    with pytest.raises(HTTPException) as exc:
        request.send(None)
    assert exc.value.status_code == 410
