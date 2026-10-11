from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.core.auth import require_authenticated_user
from app.main import app
from app.repositories import reports


client = TestClient(app)


def test_only_active_registered_production_points_are_recommended(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr(reports, "DATABASE_PATH", tmp_path / "points.db")
    app.dependency_overrides[require_authenticated_user] = lambda: {
        "id": "participant", "role": "user",
    }
    try:
        with reports._connect() as database:
            reports.initialize_database(database)
            for identifier, active, origin in (
                ("real", 1, "production"), ("inactive", 0, "production"),
                ("demo", 1, "demo"),
            ):
                database.execute(
                    """INSERT INTO recycling_points
                       (id, name, latitude, longitude, accepted_materials_json,
                        active, data_origin, created_at, updated_at)
                       VALUES (?, ?, 6.4, 100.2, '["Plastic"]', ?, ?, 'now', 'now')""",
                    (identifier, identifier, active, origin),
                )
        response = client.get("/api/recycling/points")
        assert response.status_code == 200
        assert [point["id"] for point in response.json()] == ["real"]
        assert response.json()[0]["accepted_materials"] == ["Plastic"]
    finally:
        app.dependency_overrides.clear()


def test_admin_can_create_edit_and_deactivate_without_deleting_history(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr(reports, "DATABASE_PATH", tmp_path / "points.db")
    app.dependency_overrides[require_authenticated_user] = lambda: {
        "id": "admin", "role": "admin", "email_verified": True,
    }
    payload = {
        "name": "  Campus collection point  ", "latitude": 6.4, "longitude": 100.2,
        "accepted_materials": [" Plastic ", "plastic", "Paper"],
        "description": "Near a campus facility", "active": True,
    }
    try:
        created = client.post("/api/recycling/admin/points", json=payload)
        assert created.status_code == 201
        point = created.json()
        assert point["name"] == "Campus collection point"
        assert point["accepted_materials"] == ["Plastic", "Paper"]
        identifier = point["id"]
        listed = client.get("/api/recycling/admin/points")
        assert [item["id"] for item in listed.json()] == [identifier]
        updated = client.put(f"/api/recycling/admin/points/{identifier}", json={
            **payload, "accepted_materials": ["Metal"], "active": False,
        })
        assert updated.status_code == 200
        assert updated.json()["active"] is False
        assert updated.json()["accepted_materials"] == ["Metal"]
        with reports._connect() as database:
            assert database.execute("SELECT id FROM recycling_points WHERE id = ?", (identifier,)).fetchone()
        assert client.put("/api/recycling/admin/points/missing", json=payload).status_code == 404
        assert client.post("/api/recycling/admin/points", json={**payload, "accepted_materials": []}).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_participant_cannot_manage_points(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(reports, "DATABASE_PATH", tmp_path / "points.db")
    app.dependency_overrides[require_authenticated_user] = lambda: {
        "id": "participant", "role": "user", "email_verified": True,
    }
    try:
        assert client.get("/api/recycling/admin/points").status_code == 403
        assert client.post("/api/recycling/admin/points", json={
            "name": "Point", "latitude": 6.4, "longitude": 100.2,
            "accepted_materials": ["Paper"], "active": True,
        }).status_code == 403
    finally:
        app.dependency_overrides.clear()
