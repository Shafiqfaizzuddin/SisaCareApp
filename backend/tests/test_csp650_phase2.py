"""Staff ownership, serial transitions, proof and route authorization."""
from __future__ import annotations

import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.auth import require_admin_user, require_authenticated_user, require_staff_user
from app.core.auth import authenticate_access_token
from app.core.config import Settings
from app.main import app
from app.repositories import reports, staff
from app.services import collection_workflow as workflow


@pytest.fixture()
def workflow_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(reports, "DATABASE_PATH", tmp_path / "phase2.db")
    monkeypatch.setattr(reports, "REPORT_ASSETS_DIR", tmp_path / "assets")
    admin, worker, other = [str(uuid4()) for _ in range(3)]
    report_id = uuid4().hex
    with reports._connect() as db:
        reports.initialize_database(db); staff.initialize(db)
        db.execute("""INSERT INTO reports
            (id, reference, reporter_role, user_id, title, summary, category, location,
             status, validation_status, created_at, updated_at)
             VALUES (?, ?, 'user', ?, 'Waste', 'Roadside waste', 'Bulky Waste', 'Street',
             'verified', 'valid', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')""",
                   (report_id, "SC-001", str(uuid4())))
    staff.set_grant(worker, "staff", admin)
    staff.set_grant(other, "driver", admin)
    return report_id, admin, worker, other, tmp_path


def test_positive_collection_and_verified_resolution(workflow_db) -> None:
    report_id, admin, worker, _, tmp_path = workflow_db
    assert workflow.assign(report_id, worker, "North crew", admin)["status"] == "assigned"
    assert workflow.change(report_id, "start", worker)["status"] == "in_progress"
    photo = tmp_path / "proof.jpg"; photo.write_bytes(b"validated by the API")
    assert workflow.change(report_id, "submit", worker, proof_source=photo, note="Waste removed")["status"] == "pending_verification"
    resolved = workflow.change(report_id, "verify", admin)
    assert resolved["status"] == "resolved" and resolved["resolution_seconds"] > 0
    with reports._connect() as db:
        events = db.execute("SELECT actor_id, previous_status, new_status, reason FROM report_status_events WHERE report_id = ? ORDER BY created_at, rowid", (report_id,)).fetchall()
        assert [(item["previous_status"], item["new_status"]) for item in events] == [
            ("verified", "assigned"), ("assigned", "in_progress"),
            ("in_progress", "pending_verification"), ("pending_verification", "resolved")]
        assert events[-1]["actor_id"] == admin
        assert db.execute("SELECT COUNT(*) FROM cleanup_proofs WHERE report_id = ?", (report_id,)).fetchone()[0] == 1


def test_duplicate_assignment_wrong_owner_and_missing_proof(workflow_db) -> None:
    report_id, admin, worker, other, _ = workflow_db
    with pytest.raises(workflow.TaskForbidden): workflow.assign(report_id, str(uuid4()), "Crew", admin)
    workflow.assign(report_id, worker, "Crew", admin)
    with pytest.raises(workflow.TaskConflict): workflow.assign(report_id, worker, "Crew", admin)
    with pytest.raises(workflow.TaskForbidden): workflow.change(report_id, "start", other)
    with pytest.raises(LookupError): workflow.task_for(report_id, other)
    workflow.change(report_id, "start", worker)
    with pytest.raises(ValueError, match="photo"): workflow.change(report_id, "submit", worker, note="Done")
    with pytest.raises(workflow.TaskConflict): workflow.change(report_id, "verify", admin)


def test_concurrent_assignment_has_one_active_owner(workflow_db) -> None:
    report_id, admin, worker, other, _ = workflow_db
    def attempt(user_id: str) -> str:
        try:
            workflow.assign(report_id, user_id, "Crew", admin)
            return "assigned"
        except (workflow.TaskConflict, ValueError):
            return "rejected"
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, (worker, other)))
    assert sorted(outcomes) == ["assigned", "rejected"]
    with reports._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM report_assignments WHERE report_id = ? AND ended_at IS NULL",
                          (report_id,)).fetchone()[0] == 1


def test_cleanup_proof_cannot_reference_another_assignee(workflow_db) -> None:
    report_id, admin, worker, other, _ = workflow_db
    assignment = workflow.assign(report_id, worker, "Crew", admin)
    with reports._connect() as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("""INSERT INTO cleanup_proofs
                (id, report_id, assignee_id, assignment_id, object_key, content_type, sha256, byte_size, note, created_at)
                VALUES (?, ?, ?, ?, ?, 'image/jpeg', ?, 5, 'mismatched', 'now')""",
                (uuid4().hex, report_id, other, assignment["assignment_id"], "cleanup/wrong.jpg", "a" * 64))


def test_reassignment_requires_reason_and_revokes_old_task_access(workflow_db) -> None:
    report_id, admin, worker, other, _ = workflow_db
    workflow.assign(report_id, worker, "Crew A", admin)
    with pytest.raises(ValueError, match="reason"):
        workflow.assign(report_id, other, "Crew B", admin)
    workflow.assign(report_id, other, "Crew B", admin, "Crew A unavailable")
    with pytest.raises(LookupError): workflow.task_for(report_id, worker)
    assert workflow.task_for(report_id, other)["assignment"]["assignee_id"] == other
    with reports._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM report_assignments WHERE report_id = ?", (report_id,)).fetchone()[0] == 2
        history = db.execute("SELECT previous_status, new_status, reason FROM report_status_events WHERE report_id = ? ORDER BY created_at, rowid", (report_id,)).fetchall()
        assert history[-1]["reason"] == "Crew A unavailable"
        assert history[-1]["previous_status"] == history[-1]["new_status"] == "assigned"


def test_rework_preserves_history_and_requires_new_proof(workflow_db) -> None:
    report_id, admin, worker, _, tmp_path = workflow_db
    proof = tmp_path / "proof.png"; proof.write_bytes(b"validated by the API")
    workflow.assign(report_id, worker, "Crew", admin)
    workflow.change(report_id, "start", worker)
    workflow.change(report_id, "submit", worker, proof_source=proof, note="First collection")
    with pytest.raises(ValueError, match="reason"): workflow.change(report_id, "rework", admin)
    workflow.change(report_id, "rework", admin, reason="Missed one bag")
    workflow.change(report_id, "submit", worker, proof_source=proof, note="Second collection")
    with reports._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM cleanup_proofs WHERE report_id = ?", (report_id,)).fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM report_status_events WHERE report_id = ?", (report_id,)).fetchone()[0] == 5


def test_citizen_tracking_sees_collection_status_and_history(workflow_db) -> None:
    report_id, admin, worker, _, _ = workflow_db
    with reports._connect() as db:
        owner = db.execute("SELECT user_id FROM reports WHERE id = ?", (report_id,)).fetchone()[0]
    workflow.assign(report_id, worker, "Crew", admin)
    tracking = reports.get_own_report_tracking(report_id, owner)
    assert tracking is not None and tracking["status"] == "assigned"
    assert tracking["status_events"][-1]["new_status"] == "assigned"
    assert reports.get_own_report_tracking(report_id, str(uuid4())) is None


def test_citizen_cannot_grant_assign_or_verify(workflow_db) -> None:
    report_id, _, _, _, _ = workflow_db
    citizen = {"id": str(uuid4()), "role": "user", "email_verified": True, "has_google_provider": False, "google_sub": None}
    app.dependency_overrides[require_authenticated_user] = lambda: citizen
    try:
        with TestClient(app) as client:
            assert client.post('/api/collection/admin/staff/grants', json={"user_id": str(uuid4()), "role": "staff"}).status_code == 403
            assert client.post(f'/api/collection/admin/tasks/{report_id}/assign', json={"assignee_id": str(uuid4()), "team": "Crew"}).status_code == 403
            assert client.post(f'/api/collection/admin/tasks/{report_id}/verify', json={"reason": ""}).status_code == 403
            assert client.get('/api/collection/tasks').status_code == 403
    finally: app.dependency_overrides.clear()


def test_admin_staff_grant_and_revoke_routes(workflow_db, monkeypatch: pytest.MonkeyPatch) -> None:
    _, admin, _, target, _ = workflow_db
    from app.api import collection
    async def known_user(candidate: str) -> None:
        assert candidate == target
    monkeypatch.setattr(collection, "_ensure_auth_user", known_user)
    app.dependency_overrides[require_admin_user] = lambda: {"id": admin, "role": "admin"}
    try:
        with TestClient(app) as client:
            assert client.post('/api/collection/admin/staff/grants', json={"user_id": target, "role": "admin"}).status_code == 422
            response = client.post('/api/collection/admin/staff/grants', json={"user_id": target, "role": "driver"})
            assert response.status_code == 200 and response.json()["active"] is True
            assert staff.active_role(target) == "driver"
            response = client.delete(f'/api/collection/admin/staff/grants/{target}/driver')
            assert response.status_code == 200 and response.json()["active"] is False
            assert staff.active_role(target) is None
    finally: app.dependency_overrides.clear()


def test_unassigned_staff_cannot_read_proof(workflow_db, monkeypatch: pytest.MonkeyPatch) -> None:
    report_id, admin, worker, other, tmp_path = workflow_db
    proof = tmp_path / "proof.jpg"; proof.write_bytes(b"validated by the API")
    workflow.assign(report_id, worker, "Crew", admin)
    workflow.change(report_id, "start", worker)
    workflow.change(report_id, "submit", worker, proof_source=proof, note="Done")
    with reports._connect() as db:
        proof_id = db.execute("SELECT id FROM cleanup_proofs WHERE report_id = ?", (report_id,)).fetchone()[0]
    app.dependency_overrides[require_authenticated_user] = lambda: {"id": other, "role": "staff"}
    try:
        with TestClient(app) as client:
            assert client.get(f'/api/collection/tasks/{report_id}/proof/{proof_id}').status_code == 404
    finally: app.dependency_overrides.clear()


def test_cleanup_upload_rejects_type_and_missing_photo(workflow_db) -> None:
    report_id, admin, worker, _, _ = workflow_db
    workflow.assign(report_id, worker, "Crew", admin)
    workflow.change(report_id, "start", worker)
    app.dependency_overrides[require_staff_user] = lambda: {"id": worker, "role": "staff"}
    try:
        with TestClient(app) as client:
            assert client.post(f'/api/collection/tasks/{report_id}/submit', data={"note": "Done"}).status_code == 422
            response = client.post(f'/api/collection/tasks/{report_id}/submit', data={"note": "Done"},
                                   files={"image": ("proof.txt", b"not an image", "text/plain")})
            assert response.status_code == 415
            response = client.post(f'/api/collection/tasks/{report_id}/submit', data={"note": "Done"},
                                   files={"image": ("proof.jpg", b"not an image", "image/jpeg")})
            assert response.status_code == 400
    finally: app.dependency_overrides.clear()


def test_revoked_grant_blocks_active_task(workflow_db) -> None:
    report_id, admin, worker, _, _ = workflow_db
    workflow.assign(report_id, worker, "Crew", admin)
    staff.set_grant(worker, "staff", admin, revoke=True)
    with pytest.raises(workflow.TaskForbidden): workflow.change(report_id, "start", worker)


def test_auth_role_comes_from_server_grant_not_user_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = str(uuid4())
    from app.repositories import staff as staff_repository
    monkeypatch.setattr(staff_repository, "active_role", lambda candidate: "staff" if candidate == user_id else None)
    payload = {"id": user_id, "email": "worker@example.com", "email_confirmed_at": "2026-01-01",
               "app_metadata": {}, "user_metadata": {"role": "admin"}, "identities": []}
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    async def authenticate():
        async with httpx.AsyncClient(transport=transport) as client:
            return await authenticate_access_token("token", Settings(_env_file=None,
                supabase_url="https://example.supabase.co", supabase_publishable_key="public"), client=client)
    user = asyncio.run(authenticate())
    assert user["role"] == "staff"


def test_role_lookup_initializes_fresh_sqlite_without_reports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reports, "DATABASE_PATH", tmp_path / "fresh.db")
    assert staff.active_role(str(uuid4())) is None
