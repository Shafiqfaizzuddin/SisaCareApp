from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
import pytest

from app.api import identity as identity_api
from app.core.auth import get_optional_authenticated_user
from app.core.config import Settings, get_settings
from app.main import app
from app.repositories import identities


client = TestClient(app)
TOKEN_ONE = "first-google-id-token-" + "a" * 100
TOKEN_TWO = "returning-google-id-token-" + "b" * 100


def test_initial_and_returning_google_completion_preserve_same_account(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr(identities, "get_settings", lambda: Settings(_env_file=None, database_path=tmp_path / "identity.db"))
    monkeypatch.setattr(identity_api, "verify_google_token", lambda _token, _settings: {
        "sub": "stable-sub", "email": "123@student.uitm.edu.my",
    })
    async def resolve(_email: str, _sub: str, _settings: Settings) -> str | None:
        return identities.google_owner_id("stable-sub")
    monkeypatch.setattr(identity_api, "ensure_no_automatic_link", resolve)
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    app.dependency_overrides[get_optional_authenticated_user] = lambda: {
        "id": "same-user", "email": "123@student.uitm.edu.my", "role": "user",
        "google_sub": "stable-sub", "has_email_identity": False, "email_verified": True,
    }
    try:
        for token in (TOKEN_ONE, TOKEN_TWO):
            assert client.post("/api/identity/google/preflight", json={"id_token": token}).status_code == 200
            completed = client.post("/api/identity/google/complete", json={"id_token": token})
            assert completed.status_code == 200, completed.text
            assert completed.json()["google_sub"] == "stable-sub"
            if token == TOKEN_ONE:
                with sqlite3.connect(tmp_path / "identity.db") as database:
                    database.execute(
                        """UPDATE member_identities SET claimed_affiliation = 'student',
                           matric_number = 'manual-123', matric_source = 'self_reported',
                           matric_status = 'pending' WHERE user_id = 'same-user'"""
                    )
            else:
                assert completed.json()["claimed_affiliation"] == "student"
                assert completed.json()["matric_number"] == "manual-123"
                assert completed.json()["matric_source"] == "self_reported"
                assert completed.json()["matric_status"] == "pending"
        with identities._connect() as database:
            rows = database.execute("SELECT user_id, google_sub FROM member_identities").fetchall()
            assert len(rows) == 1
            assert tuple(rows[0]) == ("same-user", "stable-sub")
        assert identities.google_owner_id("stable-sub") == "same-user"
    finally:
        app.dependency_overrides.clear()


def test_completion_never_links_a_different_supabase_user(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr(identities, "get_settings", lambda: Settings(_env_file=None, database_path=tmp_path / "identity.db"))
    monkeypatch.setattr(identity_api, "verify_google_token", lambda _token, _settings: {
        "sub": "stable-sub", "email": "123@student.uitm.edu.my",
    })
    identities.record_google_check(TOKEN_ONE, "existing", "same-user")
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    app.dependency_overrides[get_optional_authenticated_user] = lambda: {
        "id": "different-user", "email": "123@student.uitm.edu.my", "role": "user",
        "google_sub": "stable-sub", "has_email_identity": False, "email_verified": True,
    }
    try:
        assert client.post("/api/identity/google/complete", json={"id_token": TOKEN_ONE}).status_code == 403
        assert identities.google_owner_id("stable-sub") is None
    finally:
        app.dependency_overrides.clear()
