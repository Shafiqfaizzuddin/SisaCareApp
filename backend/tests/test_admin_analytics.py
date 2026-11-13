from __future__ import annotations

import csv
import io
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.core.auth import require_admin_user, require_authenticated_user
from app.main import app
from app.repositories import reports, staff
from app.services.admin_analytics import Filters, csv_export, snapshot
from app.services.analytics_pdf import render_pdf
from app.services.observed_grid import observed_cell


@pytest.fixture
def analytics_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(reports, "DATABASE_PATH", tmp_path / "reports.db")
    monkeypatch.setattr("app.main.dispatch_pending_report_emails", lambda: 0)
    monkeypatch.setattr("app.main.dispatch_pending_admin_notifications", lambda: 0)
    with reports._connect() as db:
        reports.initialize_database(db)
        staff.initialize(db)
        rows = [
            ("r1", "SC-1", "Plastic", "resolved", 3.071, 101.512, "2026-10-01T00:00:00+00:00"),
            ("r2", "SC-2", "Plastic", "resolved", 3.072, 101.513, "2026-10-02T00:00:00+00:00"),
            ("r3", "SC-3", "Organic", "in_progress", None, None, "2026-10-03T00:00:00+00:00"),
            ("r4", "=1+1", "=HYPERLINK(\"x\")", "resolved", 3.126, 101.663, "2026-10-04T00:00:00+00:00"),
        ]
        for report_id, ref, category, status, lat, lon, stamp in rows:
            db.execute("""INSERT INTO reports
                (id,reference,reporter_role,title,summary,category,location,status,latitude,longitude,
                 data_origin,created_at,updated_at)
                VALUES (?,?, 'user','Waste','Waste',?,'Private address',?,?,?,?,?,?)""",
                (report_id, ref, category, status, lat, lon, "production", stamp, stamp))
        for report_id, stamp in (("r1", "2026-10-02T00:00:00+00:00"),
                                 ("r2", "2026-10-05T00:00:00+00:00")):
            db.execute("""INSERT INTO report_status_events
                (id,report_id,actor_id,previous_status,new_status,created_at)
                VALUES (?,?, 'admin','pending_verification','resolved',?)""", ("e" + report_id, report_id, stamp))
        db.execute("""INSERT INTO report_status_events
            (id,report_id,actor_id,previous_status,new_status,created_at)
            VALUES ('legacy-r4','r4','admin','in_progress','resolved','2026-10-05T00:00:00+00:00')""")
        for report_id, ended in (("r1", "2026-10-02T00:00:00+00:00"),
                                  ("r2", "2026-10-05T00:00:00+00:00"), ("r3", None)):
            db.execute("""INSERT INTO report_assignments
                (id,report_id,team_name,assignee_id,assigned_by,assigned_at,ended_at)
                VALUES (?,?, 'Crew','worker','admin','2026-10-01T12:00:00+00:00',?)""",
                ("a" + report_id, report_id, ended))
        db.execute("""INSERT INTO cleanup_proofs
            (id,report_id,assignee_id,assignment_id,object_key,content_type,sha256,byte_size,note,created_at)
            VALUES ('p1','r1','worker','ar1','proof/a.jpg','image/jpeg',?,5,'done','2026-10-02T00:00:00+00:00')""",
            ("a" * 64,))
    return tmp_path


def test_metrics_and_missing_records(analytics_db):
    result = snapshot(Filters())
    m = result["metrics"]
    assert m["total_submitted"] == 4
    assert m["by_status"] == {"in_progress": 1, "resolved": 3}
    assert m["resolution_rate_percent"] == 75.0
    assert m["verified_resolution_count"] == 2
    assert m["average_resolution_hours"] == m["median_resolution_hours"] == 48.0
    assert m["resolved_without_verified_timestamp"] == 1
    assert m["missing_coordinates"] == 1
    assert m["staff"]["task_assignments"] == 3
    assert m["staff"]["active_assignments"] == 1
    assert m["staff"]["verified_completions_with_proof"] == 1
    assert sum(cell["count"] for cell in result["observed_heatmap"]) == 3
    assert all(cell["cell_key"].startswith("g1km:") for cell in result["observed_heatmap"])
    assert all(cell["south"] < cell["north"] and cell["west"] < cell["east"]
               for cell in result["observed_heatmap"])
    assert "guest_email" not in str(result)


def test_filters_empty_sets_and_csv_formula_protection(analytics_db):
    area = snapshot(Filters())["observed_heatmap"][0]["cell_key"]
    filtered = snapshot(Filters(start=date(2026, 10, 1), end=date(2026, 10, 3),
                                category="Plastic", area=area))
    assert filtered["metrics"]["total_submitted"] == 2
    assert len(filtered["observed_heatmap"]) == 1
    empty = snapshot(Filters(category="Glass"))
    assert empty["metrics"]["total_submitted"] == 0
    assert empty["metrics"]["resolution_rate_percent"] is None
    assert empty["metrics"]["average_resolution_hours"] is None
    assert render_pdf(empty).startswith(b"%PDF")
    assert len(list(csv.reader(io.StringIO(csv_export(empty).decode("utf-8-sig"))))) == 1
    parsed = list(csv.reader(io.StringIO(csv_export(snapshot(Filters())).decode("utf-8-sig"))))
    assert parsed[0] == ["reference", "category", "status", "submitted_at", "area", "verified_resolved_at"]
    assert parsed[-1][0].startswith("'=") and parsed[-1][1].startswith("'=")
    assert "Private address" not in str(parsed)


def test_observed_kilometre_cells_keep_counts_and_boundaries(analytics_db):
    first = observed_cell(3.071, 101.512)
    nearby = observed_cell(3.072, 101.513)
    assert first[0] == nearby[0]
    assert first[3] <= 3.071 <= first[4]
    assert first[5] <= 101.512 <= first[6]
    cells = snapshot(Filters())["observed_heatmap"]
    assert sum(cell["count"] for cell in cells) == 3
    assert next(cell for cell in cells if cell["cell_key"] == first[0])["count"] == 2
    with pytest.raises(ValueError):
        Filters(area="g005:61:2030")
    with pytest.raises(ValueError):
        observed_cell(float("nan"), 101.5)


def test_reassigned_task_without_final_proof_is_not_completed(analytics_db):
    with reports._connect() as db:
        db.execute("""INSERT INTO report_assignments
            (id,report_id,team_name,assignee_id,assigned_by,assigned_at,ended_at)
            VALUES ('new-r1','r1','Second crew','other','admin','2026-10-01T18:00:00+00:00','2026-10-02T00:00:00+00:00')""")
    metrics = snapshot(Filters())["metrics"]
    assert metrics["staff"]["task_assignments"] == 4
    assert metrics["staff"]["verified_completions_with_proof"] == 0


def test_pdf_content_and_authorization(analytics_db):
    payload = render_pdf(snapshot(Filters()))
    assert payload.startswith(b"%PDF")
    text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(payload)).pages)
    assert "Submitted reports" in text and "75.0%" in text
    assert "Private address" not in text
    client = TestClient(app)
    try:
        assert client.get("/api/admin/analytics").status_code == 401
        assert client.get("/api/admin/analytics/export.csv").status_code == 401
        assert client.get("/api/admin/analytics/export.pdf").status_code == 401
        app.dependency_overrides[require_authenticated_user] = lambda: {"id": "citizen", "role": "user"}
        try:
            assert client.get("/api/admin/analytics").status_code == 403
            assert client.get("/api/admin/analytics/export.csv").status_code == 403
        finally:
            app.dependency_overrides.clear()
        app.dependency_overrides[require_admin_user] = lambda: {"id": "admin", "role": "admin"}
        try:
            assert client.get("/api/admin/analytics").json()["metrics"]["total_submitted"] == 4
            assert client.get("/api/admin/analytics?start=2026-10-05&end=2026-10-01").status_code == 422
            csv_response = client.get("/api/admin/analytics/export.csv?category=Plastic")
            assert csv_response.status_code == 200 and len(list(csv.reader(io.StringIO(csv_response.text.lstrip("\ufeff"))))) == 3
            pdf_response = client.get("/api/admin/analytics/export.pdf")
            assert pdf_response.status_code == 200 and pdf_response.content.startswith(b"%PDF")
        finally:
            app.dependency_overrides.clear()
    finally:
        client.close()
