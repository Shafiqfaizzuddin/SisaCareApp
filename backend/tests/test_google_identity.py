import asyncio
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from pathlib import Path
import sqlite3

from app.core.config import Settings
from app.core.google_identity import (
    ensure_no_automatic_link,
    normalized_email_domain,
    suggested_matric,
    verify_google_token,
)
from app.core.auth import require_authenticated_user
from app.repositories import identities


def settings() -> Settings:
    return Settings(
        _env_file=None,
        supabase_url="https://example.supabase.co",
        supabase_publishable_key="publishable",
        supabase_service_role_key=SecretStr("secret"),
        google_client_id="client.apps.googleusercontent.com",
    )


@pytest.mark.parametrize("email,expected", [
    ("2025516823@student.uitm.edu.my", "2025516823"),
    ("20255X@student.uitm.edu.my", None),
    ("123@uitm.edu.my", None),
    ("123@gmail.com", None),
])
def test_matric_suggestion(email: str, expected: str | None) -> None:
    assert suggested_matric(email) == expected


def test_domain_is_exact_and_normalized() -> None:
    assert normalized_email_domain(" X@STUDENT.UITM.EDU.MY ") == "student.uitm.edu.my"
    assert normalized_email_domain("x@fakeuitm.edu.my") != "uitm.edu.my"


def test_google_token_checks_verified_email_and_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.google_identity.id_token.verify_oauth2_token",
        lambda *_args: {"sub": "stable-123", "email": "123@STUDENT.UITM.EDU.MY", "email_verified": True},
    )
    assert verify_google_token("token", settings()) == {
        "sub": "stable-123", "email": "123@student.uitm.edu.my"
    }
    monkeypatch.setattr(
        "app.core.google_identity.id_token.verify_oauth2_token",
        lambda *_args: {"sub": "stable-123", "email": "person@gmail.com", "email_verified": True},
    )
    with pytest.raises(HTTPException) as exc:
        verify_google_token("token", settings())
    assert exc.value.status_code == 403
    monkeypatch.setattr(
        "app.core.google_identity.id_token.verify_oauth2_token",
        lambda *_args: {"sub": "stable-123", "email": "staff@uitm.edu.my", "email_verified": True},
    )
    assert verify_google_token("token", settings())["email"] == "staff@uitm.edu.my"
    monkeypatch.setattr(
        "app.core.google_identity.id_token.verify_oauth2_token",
        lambda *_args: {"sub": "stable-123", "email": "staff@uitm.edu.my", "email_verified": False},
    )
    with pytest.raises(HTTPException) as exc:
        verify_google_token("token", settings())
    assert exc.value.status_code == 403
    def invalid_token(*_args: object) -> None:
        raise ValueError("invalid")
    monkeypatch.setattr("app.core.google_identity.id_token.verify_oauth2_token", invalid_token)
    with pytest.raises(HTTPException) as exc:
        verify_google_token("token", settings())
    assert exc.value.status_code == 401


def test_existing_email_requires_explicit_link(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(identities, "get_settings", lambda: Settings(_env_file=None, database_path=tmp_path / "identity.db"))
    async def check() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"id": "website-user", "email": "a@student.uitm.edu.my", "identities": [{"provider": "email"}]})
            if request.url.path.endswith("/website-user") else httpx.Response(200, json={"users": [{
                "id": "website-user", "email": "a@student.uitm.edu.my"
            }]})
        )) as client:
            await ensure_no_automatic_link("a@student.uitm.edu.my", "sub-1", settings(), client=client)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(check())
    assert exc.value.status_code == 409


def test_returning_google_user_uses_detail_identity_when_admin_list_omits_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr(identities, "get_settings", lambda: Settings(_env_file=None, database_path=tmp_path / "identity.db"))
    identities.save_google_sub("google-user", "123@student.uitm.edu.my", "stable-sub")
    async def check() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={
                "id": "google-user", "email": "123@student.uitm.edu.my",
                "identities": [{"provider": "google", "id": "identity-uuid", "identity_data": {"sub": "stable-sub"}}],
            }) if request.url.path.endswith("/google-user") else httpx.Response(200, json={"users": [{
                "id": "google-user", "email": "123@student.uitm.edu.my"
            }]})
        )) as client:
            assert await ensure_no_automatic_link("123@student.uitm.edu.my", "stable-sub", settings(), client=client) == "google-user"
    asyncio.run(check())


def test_trusted_provider_repairs_missing_local_google_subject(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr(identities, "get_settings", lambda: Settings(_env_file=None, database_path=tmp_path / "identity.db"))
    async def check() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={
                "id": "google-user", "email": "123@student.uitm.edu.my",
                "identities": [{"provider": "google", "identity_data": {"sub": "stable-sub"}}],
            }) if request.url.path.endswith("/google-user") else httpx.Response(200, json={"users": [{
                "id": "google-user", "email": "123@student.uitm.edu.my"
            }]})
        )) as client:
            assert await ensure_no_automatic_link("123@student.uitm.edu.my", "stable-sub", settings(), client=client) == "google-user"
    asyncio.run(check())
    assert identities.google_owner_id("stable-sub") is None  # Persist only after authenticated completion.


@pytest.mark.parametrize("trusted_sub,expected", [("stable-sub", "google-user"), (None, 409), ("other-sub", 409)])
def test_orphaned_google_origin_requires_trusted_subject_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, trusted_sub: str | None, expected: str | int,
) -> None:
    monkeypatch.setattr(identities, "get_settings", lambda: Settings(_env_file=None, database_path=tmp_path / "identity.db"))
    async def check() -> str | None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={
                "id": "google-user", "email": "123@student.uitm.edu.my", "identities": [],
                "app_metadata": {"provider": "google", **({"google_sub": trusted_sub} if trusted_sub else {})},
            }) if request.url.path.endswith("/google-user") else httpx.Response(200, json={"users": [{
                "id": "google-user", "email": "123@student.uitm.edu.my"
            }]})
        )) as client:
            return await ensure_no_automatic_link("123@student.uitm.edu.my", "stable-sub", settings(), client=client)
    if isinstance(expected, int):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(check())
        assert exc.value.status_code == expected
    else:
        assert asyncio.run(check()) == expected


def test_direct_google_session_requires_server_completion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr(identities, "get_settings", lambda: Settings(_env_file=None, database_path=tmp_path / "identity.db"))
    user = {
        "id": "google-user", "email": "123@student.uitm.edu.my", "role": "user",
        "email_verified": True, "google_sub": "sub-1", "google_email": "123@student.uitm.edu.my",
        "has_email_identity": False,
        "has_google_provider": True,
    }
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_authenticated_user(user))
    assert exc.value.status_code == 403


def test_matric_from_verified_email_does_not_replace_verified_value(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    db_path = tmp_path / "identity.db"
    monkeypatch.setattr(identities, "get_settings", lambda: Settings(_env_file=None, database_path=db_path))
    first = identities.read_identity("user-1", "2025516823@student.uitm.edu.my", email_verified=True)
    assert first["matric_number"] == "2025516823"
    assert first["matric_source"] == "verified_email"
    with sqlite3.connect(db_path) as database:
        database.execute("UPDATE member_identities SET matric_number = '999', matric_verified = 1 WHERE user_id = 'user-1'")
    later = identities.read_identity("user-1", "123@student.uitm.edu.my", email_verified=True)
    assert later["matric_number"] == "999"


def test_google_check_is_one_time_and_new_flow_cannot_link_website_account(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr(identities, "get_settings", lambda: Settings(_env_file=None, database_path=tmp_path / "identity.db"))
    identities.record_google_check("token-one", "new")
    assert not identities.consume_google_check("token-one", "website-user", has_email_identity=True)
    assert identities.consume_google_check("token-one", "new-google-user", has_email_identity=False)
    assert identities.consume_google_check("token-one", "new-google-user", has_email_identity=False)
    assert not identities.consume_google_check("token-one", "different-user", has_email_identity=False)
    identities.record_google_check("token-two", "link", "website-user")
    assert not identities.consume_google_check("token-two", "different-user", has_email_identity=True)
    assert identities.consume_google_check("token-two", "website-user", has_email_identity=True)


def test_concurrent_google_subject_writes_have_one_owner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr(identities, "get_settings", lambda: Settings(_env_file=None, database_path=tmp_path / "identity.db"))
    identities.read_identity("first", "first@student.uitm.edu.my", email_verified=True)
    identities.read_identity("second", "second@student.uitm.edu.my", email_verified=True)

    def connect(user_id: str) -> str:
        try:
            identities.save_google_sub(user_id, f"{user_id}@student.uitm.edu.my", "same-sub")
            return "connected"
        except ValueError:
            return "collision"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(connect, ["first", "second"]))
    assert sorted(results) == ["collision", "connected"]
    assert identities.google_owner_id("same-sub") in {"first", "second"}
    with identities._connect() as database:
        assert database.execute("SELECT count(*) FROM member_identities WHERE google_sub = 'same-sub'").fetchone()[0] == 1


def test_staff_is_excluded_from_e_merit_even_with_a_verified_matric(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    db_path = tmp_path / "identity.db"
    monkeypatch.setattr(identities, "get_settings", lambda: Settings(_env_file=None, database_path=db_path))
    identities.read_identity("staff-1", "worker@uitm.edu.my", email_verified=True)
    with sqlite3.connect(db_path) as database:
        database.execute(
            "UPDATE member_identities SET verified_affiliation = 'staff', matric_number = '123', matric_verified = 1 WHERE user_id = 'staff-1'"
        )
    assert identities.read_identity("staff-1", "worker@uitm.edu.my", email_verified=True)["e_merit_identity_eligible"] is False


def test_matric_suggestion_requires_verified_email_and_student_eligibility_requires_admin_verification(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    db_path = tmp_path / "identity.db"
    monkeypatch.setattr(identities, "get_settings", lambda: Settings(_env_file=None, database_path=db_path))
    unverified = identities.read_identity("student-1", "2025516823@student.uitm.edu.my", email_verified=False)
    assert unverified["matric_number"] is None
    suggested = identities.read_identity("student-1", "2025516823@student.uitm.edu.my", email_verified=True)
    assert suggested["matric_number"] == "2025516823"
    assert suggested["e_merit_identity_eligible"] is False
    manual = identities.read_identity("student-2", "name@student.uitm.edu.my", email_verified=True)
    assert manual["matric_number"] is None
    submitted = identities.submit_matric("student-1", "2025516823@student.uitm.edu.my", "2025516823")
    assert submitted["matric_status"] == "pending"
    assert submitted["e_merit_identity_eligible"] is False
    identities.review_matric("student-1", "admin-1", "verified", "prototype_manual", "Agreed student register checked", None)
    assert identities.read_identity("student-1", "2025516823@student.uitm.edu.my", email_verified=True)["e_merit_identity_eligible"] is True
