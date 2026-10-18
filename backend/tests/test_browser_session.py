from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import browser_session as api
from app.main import app
from app.repositories import browser_sessions, reports


USER = {"id": "student-1", "email": "student@example.com", "role": "user",
        "email_verified": True, "google_sub": None, "google_email": None,
        "has_email_identity": True, "has_google_provider": False}


@pytest.fixture
def session_setup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    settings = SimpleNamespace(database_path=tmp_path / "sessions.db", session_idle_seconds=60,
                               session_absolute_seconds=300, session_cookie_secure=False)
    monkeypatch.setattr(browser_sessions, "get_settings", lambda: settings)
    monkeypatch.setattr(reports, "DATABASE_PATH", settings.database_path)
    async def validate(_token, _settings):
        return USER
    monkeypatch.setattr(api, "authenticate_access_token", validate)
    clock = {"now": 1000}
    monkeypatch.setattr(browser_sessions.time, "time", lambda: clock["now"])
    return clock


def test_cookie_session_refresh_logout_and_return_login(session_setup: dict[str, int]) -> None:
    with TestClient(app) as client:
        started = client.post("/api/auth/session", headers={"Authorization": "Bearer sample"})
        assert started.status_code == 200
        cookie = started.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=lax" in cookie and "max-age" not in cookie
        assert client.get("/api/auth/session").json()["user_id"] == "student-1"
        session_setup["now"] += 30
        assert client.get("/api/auth/session").status_code == 200
        assert client.delete("/api/auth/session").status_code == 204
        assert client.get("/api/auth/session").status_code == 401
        assert client.post("/api/auth/session", headers={"Authorization": "Bearer sample"}).status_code == 200


def test_idle_and_absolute_expiry_even_when_cookie_is_restored(session_setup: dict[str, int]) -> None:
    with TestClient(app) as first_tab:
        first_tab.post("/api/auth/session", headers={"Authorization": "Bearer sample"})
        cookie = first_tab.cookies.get("sisacare_session")
        assert cookie
        with TestClient(app, cookies={"sisacare_session": cookie}) as second_tab:
            assert second_tab.get("/api/auth/session").status_code == 200
            session_setup["now"] += 61
            assert first_tab.get("/api/auth/session").status_code == 401
            assert second_tab.get("/api/auth/session").status_code == 401
        first_tab.post("/api/auth/session", headers={"Authorization": "Bearer sample"})
        for _ in range(5):
            session_setup["now"] += 55
            assert first_tab.get("/api/auth/session").status_code == 200
        session_setup["now"] += 26
        assert first_tab.get("/api/auth/session").status_code == 401
