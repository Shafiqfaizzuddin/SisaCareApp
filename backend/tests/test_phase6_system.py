"""Controlled three-role API journey; no external identities or SMTP are claimed."""
from __future__ import annotations

import base64
import json
import sqlite3
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from app.core.auth import require_admin_user, require_authenticated_user, require_staff_user
from app.core.config import Settings
from app.main import app
from app.repositories import reports, staff
from app.services import report_email

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


def test_three_role_report_to_resolution_and_exports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(reports, "DATABASE_PATH", tmp_path / "reports.db")
    monkeypatch.setattr(reports, "REPORT_ASSETS_DIR", tmp_path / "assets")
    from app.api import reports as report_api
    from app.api import collection as collection_api
    monkeypatch.setattr(report_api, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(collection_api, "UPLOAD_DIR", tmp_path / "uploads")
    citizen_id, admin_id, staff_id = [str(uuid4()) for _ in range(3)]
    citizen = {"id": citizen_id, "email": "citizen@example.com", "role": "user",
               "email_verified": True, "google_sub": None, "google_email": None,
               "has_email_identity": True, "has_google_provider": False}
    admin = {**citizen, "id": admin_id, "email": "admin@example.com", "role": "admin"}
    worker = {**citizen, "id": staff_id, "email": "worker@example.com", "role": "staff"}
    app.dependency_overrides[require_authenticated_user] = lambda: citizen
    app.dependency_overrides[require_admin_user] = lambda: admin
    app.dependency_overrides[require_staff_user] = lambda: worker
    payload = {
        "analysis_id": None, "reporter_role": "user", "title": "Plastic waste near park",
        "summary": "Citizen corrected the drafted description.", "category": "Recyclable Waste",
        "confirmed_items": [{"name": "Plastic Bottle", "category": "Recyclable Waste", "material": "Plastic"}],
        "location": "Park entrance", "latitude": 6.4436, "longitude": 100.27,
        "location_source": "map", "site_notes": "Accessible from the road.",
    }
    settings = Settings(_env_file=None, user_smtp_host="smtp.example.com",
                        user_smtp_from="updates@example.com", email_public_base_url="https://sisacare.example")
    sent = []
    monkeypatch.setattr(report_email, "_send", lambda message, *_: sent.append(message))
    try:
        with TestClient(app) as client:
            bad = client.post("/api/reports/with-image", data={"payload": json.dumps(payload)},
                              files={"image": ("bad.txt", b"not an image", "text/plain")})
            assert bad.status_code == 415
            created = client.post("/api/reports/with-image", data={"payload": json.dumps(payload)},
                                  files={"image": ("waste.png", PNG, "image/png")})
            assert created.status_code == 201, created.text
            report_id = created.json()["id"]
            with reports._connect() as db:
                row = db.execute("SELECT status,summary,latitude,longitude FROM reports WHERE id = ?", (report_id,)).fetchone()
                assert tuple(row) == ("submitted", payload["summary"], 6.4436, 100.27)
            assert client.get(f"/api/members/me/reports/{report_id}").status_code == 200
            assert client.post(f"/api/reports/{report_id}/validation", json={"validation_status": "valid"}).status_code == 200
            staff.set_grant(staff_id, "staff", admin_id)
            assigned = client.post(f"/api/collection/admin/tasks/{report_id}/assign",
                                   json={"assignee_id": staff_id, "team": "North crew"})
            assert assigned.status_code == 200, assigned.text
            assert client.post(f"/api/collection/tasks/{report_id}/start").status_code == 200
            assert client.post(f"/api/collection/tasks/{report_id}/submit", data={"note": "Collected"},
                               files={"image": ("cleanup.png", PNG, "image/png")}).status_code == 200
            assert client.post(f"/api/collection/admin/tasks/{report_id}/verify",
                               json={"reason": "Proof accepted"}).status_code == 200
            timeline = client.get(f"/api/members/me/reports/{report_id}").json()
            assert timeline["status"] == "resolved"
            assert [event["new_status"] for event in timeline["status_events"]][-4:] == [
                "assigned", "in_progress", "pending_verification", "resolved"]
            assert client.get("/api/admin/analytics").json()["metrics"]["total_submitted"] == 1
            assert client.get("/api/admin/analytics").json()["metrics"]["verified_resolution_count"] == 1
            assert client.get("/api/admin/analytics/export.csv").status_code == 200
            assert client.get("/api/admin/analytics/export.pdf").content.startswith(b"%PDF")
            assert report_email.dispatch_pending_report_emails(settings) == 1
            assert sum("resolved" in str(message["Subject"]).lower() for message in sent) == 1
            assert client.get("/api/admin/notifications/email?status=sent").json()["events"][0]["delivery_status"] == "sent"
    finally:
        app.dependency_overrides.clear()


def test_database_outage_rejects_submission_and_removes_temporary_upload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    from app.api import reports as report_api
    monkeypatch.setattr(report_api, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(reports, "_connect", lambda: (_ for _ in ()).throw(sqlite3.OperationalError("offline")))
    app.dependency_overrides[require_authenticated_user] = lambda: {
        "id": str(uuid4()), "email": "citizen@example.com", "email_verified": True, "role": "user",
    }
    payload = {
        "analysis_id": None, "reporter_role": "user", "title": "Park waste",
        "summary": "Plastic waste near the path.", "category": "Recyclable Waste",
        "confirmed_items": [{"name": "Plastic Bottle", "category": "Recyclable Waste", "material": "Plastic"}],
        "location": "Park entrance", "latitude": 6.4, "longitude": 100.2, "location_source": "map",
    }
    try:
        with TestClient(app) as client:
            result = client.post("/api/reports/with-image", data={"payload": json.dumps(payload)},
                                 files={"image": ("waste.png", PNG, "image/png")})
            assert result.status_code == 500
            assert result.json()["detail"] == "The report could not be stored. Please try again."
            assert list((tmp_path / "uploads").iterdir()) == []
    finally:
        app.dependency_overrides.clear()
