"""Phase 1 migration and private-storage regression checks."""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.auth import require_admin_user, require_authenticated_user
from app.main import app
from app.repositories.postgres_compat import Record, translate_sql
from app.services import supabase_storage


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("csp650_migration", ROOT / "scripts" / "migrate_sqlite_to_supabase.py")
assert SPEC and SPEC.loader
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


def test_sqlite_source_is_read_only_and_detects_orphan(tmp_path: Path) -> None:
    path = tmp_path / "source.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE parent (id TEXT PRIMARY KEY)")
        db.execute("CREATE TABLE child (id TEXT PRIMARY KEY, parent_id TEXT REFERENCES parent(id))")
        db.execute("PRAGMA foreign_keys = OFF")
        db.execute("INSERT INTO child VALUES ('orphan', 'missing')")
    db = migration.source_connection(path)
    try:
        with pytest.raises(sqlite3.OperationalError):
            db.execute("INSERT INTO parent VALUES ('new')")
        assert list(db.execute("PRAGMA foreign_key_check"))
    finally:
        db.close()


def test_asset_manifest_rejects_missing_private_image(tmp_path: Path) -> None:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE reports (id TEXT, original_image TEXT, annotated_image TEXT, after_photo TEXT)")
    db.execute("CREATE TABLE recycling_actions (id TEXT, original_photo TEXT, proof_photo TEXT)")
    db.execute("CREATE TABLE education_articles (id TEXT, image_filename TEXT)")
    report_id = "a" * 32
    db.execute("INSERT INTO reports VALUES (?, ?, NULL, NULL)",
               (report_id, f"/api/reports/files/{report_id}/original.jpg"))
    assets, errors = migration.asset_manifest(db, tmp_path)
    assert assets == []
    assert any("Missing referenced image" in error for error in errors)


def test_repeatable_row_import_rejects_conflicting_target(monkeypatch: pytest.MonkeyPatch) -> None:
    source = sqlite3.connect(":memory:")
    source.row_factory = sqlite3.Row
    source.execute("CREATE TABLE reports (id TEXT PRIMARY KEY, title TEXT NOT NULL)")
    source.execute("INSERT INTO reports VALUES ('r1', 'Original')")
    target = sqlite3.connect(":memory:")
    target.execute("CREATE TABLE reports (id TEXT PRIMARY KEY, title TEXT NOT NULL)")

    class Target:
        def execute(self, statement, parameters=()):
            return target.execute(statement.replace("sisacare.", "").replace("%s", "?"), parameters)

    monkeypatch.setattr(migration, "TABLE_ORDER", ("reports",))
    assert migration.import_rows(source, Target()) == {"reports": 1}
    assert migration.import_rows(source, Target()) == {"reports": 1}
    assert target.execute("SELECT COUNT(*) FROM reports").fetchone()[0] == 1
    target.execute("UPDATE reports SET title = 'Changed' WHERE id = 'r1'")
    with pytest.raises(ValueError, match="Conflicting existing row"):
        migration.import_rows(source, Target())


def test_postgres_adapter_preserves_legacy_parameter_and_row_contract() -> None:
    assert translate_sql("INSERT OR IGNORE INTO report_email_outbox VALUES (?, ?)") == (
        "INSERT INTO report_email_outbox VALUES (%s, %s) ON CONFLICT DO NOTHING"
    )
    assert translate_sql("SELECT * FROM report_status_events ORDER BY created_at, rowid") == (
        "SELECT * FROM report_status_events ORDER BY created_at, id"
    )
    row = Record((("id", "r1"), ("status", "submitted")))
    assert row[0] == row["id"] == "r1"
    assert dict(row)["status"] == "submitted"


def test_storage_requires_server_credential_and_never_uses_public_url(monkeypatch: pytest.MonkeyPatch,
                                                                        tmp_path: Path) -> None:
    image = tmp_path / "original.jpg"
    image.write_bytes(b"image bytes")
    monkeypatch.setattr(supabase_storage, "get_settings", lambda: SimpleNamespace(
        supabase_url="https://project.supabase.co", max_upload_size=1000,
        supabase_service_role_key=SimpleNamespace(get_secret_value=lambda: ""),
    ))
    with pytest.raises(RuntimeError, match="credential"):
        supabase_storage.put_file("reports/r1/original.jpg", image)
    assert "/storage/v1/object/sisacare-private/reports/r1/original.jpg" in supabase_storage._object_url(
        "reports/r1/original.jpg"
    )


def test_report_image_requires_admin_before_storage_access(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import reports as reports_api

    accessed = []
    monkeypatch.setattr(reports_api, "get_settings", lambda: SimpleNamespace(persistence_backend="postgres"))
    monkeypatch.setattr(supabase_storage, "get_file", lambda key: accessed.append(key) or b"private")
    app.dependency_overrides[require_authenticated_user] = lambda: {"id": "citizen", "role": "user"}
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/reports/files/{'a' * 32}/original.jpg")
        assert response.status_code == 403
        assert accessed == []
    finally:
        app.dependency_overrides.clear()


def test_admin_image_uses_registered_private_object(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import reports as reports_api

    report_id = "b" * 32
    calls = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, _statement, parameters):
            calls.append(parameters)
            return self

        def fetchone(self):
            return {"object_key": f"reports/{report_id}/original.jpg"}

    monkeypatch.setattr(reports_api, "get_settings", lambda: SimpleNamespace(persistence_backend="postgres"))
    monkeypatch.setattr(reports_api.report_repository, "_connect", lambda: Connection())
    monkeypatch.setattr(supabase_storage, "get_file", lambda key: b"private-data" if key == f"reports/{report_id}/original.jpg" else b"")
    app.dependency_overrides[require_admin_user] = lambda: {"id": "admin", "role": "admin"}
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/reports/files/{report_id}/original.jpg")
        assert response.status_code == 200
        assert response.content == b"private-data"
        assert response.headers["cache-control"] == "private, no-store"
        assert calls == [(report_id, f"reports/{report_id}/original.jpg")]
    finally:
        app.dependency_overrides.clear()
