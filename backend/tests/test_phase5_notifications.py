"""Citizen workflow email outbox and delivery-state regression tests."""
from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.auth import require_admin_user, require_authenticated_user
from app.core.config import Settings
from app.main import app
from app.repositories import reports, staff
from app.services import collection_workflow as workflow, report_email


@pytest.fixture
def task(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(reports, "DATABASE_PATH", tmp_path / "reports.db")
    monkeypatch.setattr(reports, "REPORT_ASSETS_DIR", tmp_path / "assets")
    admin, worker = str(uuid4()), str(uuid4())
    report_id = uuid4().hex
    with reports._connect() as db:
        reports.initialize_database(db); staff.initialize(db)
        db.execute("""INSERT INTO reports
            (id,reference,reporter_role,user_id,title,summary,category,location,status,
             validation_status,notification_email,created_at,updated_at)
            VALUES (?, 'SCA-200', 'user', ?, 'Roadside waste', 'Waste', 'Recyclable Waste',
                    'Private address', 'verified', 'valid', 'citizen@example.com',
                    '2026-10-01T00:00:00+00:00', '2026-10-01T00:00:00+00:00')""", (report_id, str(uuid4())))
    staff.set_grant(worker, "staff", admin)
    proof = tmp_path / "proof.jpg"
    proof.write_bytes(b"validated before workflow service")
    return report_id, admin, worker, proof, tmp_path


def _settings(**values) -> Settings:
    return Settings(_env_file=None, email_public_base_url="https://sisacare.example", **values)


def _complete(task):
    report_id, admin, worker, proof, _ = task
    workflow.assign(report_id, worker, "Crew", admin)
    workflow.change(report_id, "start", worker)
    workflow.change(report_id, "submit", worker, proof_source=proof, note="Cleaned")
    return workflow.change(report_id, "verify", admin)


def test_resolved_event_survives_unconfigured_smtp_and_sends_once(task, monkeypatch):
    monkeypatch.setattr(workflow, "get_settings", lambda: _settings())
    report_id, admin, _, _, _ = task
    assert _complete(task)["status"] == "resolved"
    with reports._connect() as db:
        outbox = db.execute("SELECT event_key,event_type,recipient_email FROM report_email_outbox").fetchall()
        notification = db.execute("SELECT event_type,delivery_status,attempts FROM notifications").fetchone()
    assert len(outbox) == 1 and outbox[0]["event_type"] == "resolved"
    assert outbox[0]["recipient_email"] == "citizen@example.com"
    assert tuple(notification) == ("resolved", "queued", 0)
    assert report_email.dispatch_pending_report_emails(_settings()) == 0
    sent = []
    monkeypatch.setattr(report_email, "_send", lambda message, *_: sent.append(message))
    configured = _settings(user_smtp_host="smtp.example.com", user_smtp_from="updates@example.com")
    assert report_email.dispatch_pending_report_emails(configured) == 1
    assert report_email.dispatch_pending_report_emails(configured) == 0
    assert len(sent) == 1
    assert "Current status: Resolved" in sent[0].get_body(preferencelist=("plain",)).get_content()
    assert f"/account/reports/{report_id}" in sent[0].get_body(preferencelist=("plain",)).get_content()
    with reports._connect() as db:
        assert db.execute("SELECT delivery_status FROM notifications").fetchone()[0] == "sent"
        assert db.execute("SELECT status FROM reports WHERE id = ?", (report_id,)).fetchone()[0] == "resolved"
    with pytest.raises(workflow.TaskConflict): workflow.change(report_id, "verify", admin)


def test_optional_updates_and_reassignment_use_distinct_event_keys(task, monkeypatch):
    monkeypatch.setattr(workflow, "get_settings", lambda: _settings(
        notify_citizen_on_assignment=True, notify_citizen_on_progress=True))
    report_id, admin, worker, proof, _ = task
    other = str(uuid4()); staff.set_grant(other, "driver", admin)
    workflow.assign(report_id, worker, "Crew A", admin)
    workflow.assign(report_id, other, "Crew B", admin, reason="Shift changed")
    workflow.change(report_id, "start", other)
    workflow.change(report_id, "submit", other, proof_source=proof, note="Cleaned")
    workflow.change(report_id, "verify", admin)
    with reports._connect() as db:
        rows = db.execute("SELECT event_key,event_type FROM report_email_outbox ORDER BY created_at,rowid").fetchall()
        assert [row["event_type"] for row in rows] == ["assigned", "assigned", "in_progress", "pending_verification", "resolved"]
        assert len({row["event_key"] for row in rows}) == 5
        assert db.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == 5
    event = {"event_type": "pending_verification", "event_key": rows[3]["event_key"],
             "recipient_email": "citizen@example.com", "report_id": report_id,
             "reference": "SCA-200", "title": "Waste", "location": "Private address"}
    message = report_email.build_report_message(event, _settings(user_smtp_from="updates@example.com"))
    assert "Current status: Pending Verification" in message.get_body(preferencelist=("plain",)).get_content()
    assert "Private address" not in message.get_body(preferencelist=("plain",)).get_content()
    assert message["Message-ID"] == report_email.build_report_message(event, _settings(user_smtp_from="updates@example.com"))["Message-ID"]


def test_failures_retry_and_admin_visibility(task, monkeypatch):
    monkeypatch.setattr(workflow, "get_settings", lambda: _settings())
    report_id, _, _, _, _ = task
    _complete(task)
    configured = _settings(user_smtp_host="smtp.example.com", user_smtp_from="updates@example.com")
    monkeypatch.setattr(report_email, "_send", lambda *_: (_ for _ in ()).throw(OSError("SMTP offline")))
    for attempt in range(5):
        with reports._connect() as db:
            db.execute("UPDATE report_email_outbox SET next_attempt_at = NULL")
        assert report_email.dispatch_pending_report_emails(configured) == 0
    with reports._connect() as db:
        event_key = db.execute("SELECT event_key FROM report_email_outbox").fetchone()[0]
        result = db.execute("SELECT delivery_status,attempts,last_error FROM notifications").fetchone()
        assert tuple(result) == ("failed", 5, "OSError")
        assert db.execute("SELECT status FROM reports WHERE id = ?", (report_id,)).fetchone()[0] == "resolved"
    client = TestClient(app)
    with client:
        assert client.get("/api/admin/notifications/email").status_code == 401
        assert client.post(f"/api/admin/notifications/email/{event_key}/retry").status_code == 401
        app.dependency_overrides[require_authenticated_user] = lambda: {"id": "citizen", "role": "user"}
        try: assert client.get("/api/admin/notifications/email").status_code == 403
        finally: app.dependency_overrides.clear()
        app.dependency_overrides[require_admin_user] = lambda: {"id": "admin", "role": "admin"}
        try:
            listing = client.get("/api/admin/notifications/email?status=failed")
            assert listing.status_code == 200
            assert listing.json()["events"][0]["recipient_hint"] == "c***@example.com"
            assert "citizen@example.com" not in listing.text
            assert client.post(f"/api/admin/notifications/email/{event_key}/retry").json()["delivery_status"] == "queued"
            assert client.post(f"/api/admin/notifications/email/{event_key}/retry").status_code == 409
        finally: app.dependency_overrides.clear()
    sent = []
    monkeypatch.setattr(report_email, "_send", lambda message, *_: sent.append(message))
    assert report_email.dispatch_pending_report_emails(configured) == 1
    assert len(sent) == 1


def test_legacy_sqlite_outbox_rows_are_preserved(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(reports, "DATABASE_PATH", tmp_path / "legacy.db")
    reports.initialize_database()
    with reports._connect() as db:
        db.execute("""INSERT INTO reports
            (id,reference,reporter_role,title,summary,category,location,status,created_at,updated_at)
            VALUES ('r1','SCA-1','user','Waste','Waste','Other','Park','submitted','2026-01-01','2026-01-01')""")
        db.execute("DROP TABLE notifications")
        db.execute("DROP TABLE report_email_outbox")
        db.execute("""CREATE TABLE report_email_outbox (
            event_key TEXT PRIMARY KEY,report_id TEXT NOT NULL REFERENCES reports(id),
            event_type TEXT NOT NULL CHECK(event_type IN ('submitted','in_progress','resolved')),
            recipient_email TEXT NOT NULL,created_at TEXT NOT NULL,sent_at TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,last_error TEXT,claimed_at TEXT,
            claim_token TEXT,next_attempt_at TEXT)""")
        db.execute("""INSERT INTO report_email_outbox(event_key,report_id,event_type,recipient_email,created_at)
            VALUES ('r1:submitted','r1','submitted','admin@example.com','2026-01-01')""")
    reports.initialize_database()
    with reports._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM report_email_outbox").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == 1
        reports._queue_email(db, "r1", "assigned", "user@example.com", "2026-01-02", event_id="transition-2")
        reports._queue_email(db, "r1", "assigned", "user@example.com", "2026-01-02", event_id="transition-2")
        assert db.execute("SELECT COUNT(*) FROM report_email_outbox").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == 2


def test_unauthorized_or_conflicting_transitions_do_not_queue_email(task, monkeypatch):
    monkeypatch.setattr(workflow, "get_settings", lambda: _settings(notify_citizen_on_assignment=True))
    report_id, admin, worker, _, _ = task
    with pytest.raises(workflow.TaskForbidden): workflow.assign(report_id, str(uuid4()), "Crew", admin)
    with reports._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM report_email_outbox").fetchone()[0] == 0
    workflow.assign(report_id, worker, "Crew", admin)
    with pytest.raises(workflow.TaskConflict): workflow.change(report_id, "verify", admin)
    with reports._connect() as db:
        assert db.execute("SELECT event_type FROM report_email_outbox").fetchall()[0][0] == "assigned"
        assert db.execute("SELECT COUNT(*) FROM report_email_outbox").fetchone()[0] == 1


def test_concurrent_sqlite_claims_lease_once(task, monkeypatch):
    monkeypatch.setattr(workflow, "get_settings", lambda: _settings())
    _complete(task)
    with ThreadPoolExecutor(max_workers=2) as pool:
        batches = list(pool.map(lambda _: reports.claim_pending_report_emails(include_admin=False), range(2)))
    assert sorted(len(batch) for batch in batches) == [0, 1]
