"""Administrator-owned staff invitations; Supabase is mocked, never contacted."""
from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4
from fastapi import HTTPException

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import collection
from app.core.auth import require_admin_user, require_authenticated_user
from app.core.config import Settings
from app.main import app
from app.repositories import reports, staff


def _complete(coroutine):
    """Drive a coroutine whose network and thread dependencies are mocked as immediate."""
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    raise AssertionError("A mocked request unexpectedly suspended.")


@pytest.fixture()
def isolated_grants(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(reports, "DATABASE_PATH", tmp_path / "staff.db")
    admin_id = str(uuid4())
    yield admin_id
    app.dependency_overrides.clear()


def test_admin_invites_new_staff_and_grant_survives_reinitialization(isolated_grants, monkeypatch):
    admin_id = isolated_grants
    invited_id = str(uuid4())
    calls = []

    async def fake_invite(invite):
        calls.append(invite)
        return {"id": invited_id, "email": invite.email}

    monkeypatch.setattr(collection, "_invite_auth_user", fake_invite)
    app.dependency_overrides[require_admin_user] = lambda: {"id": admin_id, "role": "admin"}
    with TestClient(app) as client:
        response = client.post("/api/collection/admin/staff/invite", json={
            "email": " New.Worker@Example.com ", "display_name": "  New Worker  ", "role": "driver",
        })
        assert response.status_code == 201, response.text
        assert response.json() == {"user_id": invited_id, "email": "new.worker@example.com",
                                   "role": "driver", "invitation_sent": True}
        assert calls[0].display_name == "New Worker"
        assert staff.active_role(invited_id) == "driver"
        grant = client.get("/api/collection/admin/staff").json()
        assert grant[0]["email"] == "new.worker@example.com"
        assert grant[0]["display_name"] == "New Worker"
        assert grant[0]["invited_at"]
        assert grant[0]["granted_by"] == admin_id
        with reports._connect() as db:
            staff.initialize(db)
        assert staff.active_role(invited_id) == "driver"


def test_invite_rejects_unauthorized_and_invalid_input(isolated_grants, monkeypatch):
    called = []
    async def fake_invite(invite):
        called.append(invite)
        return {"id": str(uuid4()), "email": invite.email}
    monkeypatch.setattr(collection, "_invite_auth_user", fake_invite)
    with TestClient(app) as client:
        assert client.post("/api/collection/admin/staff/invite", json={
            "email": "worker@example.com", "display_name": "Worker", "role": "staff"}).status_code == 401
        app.dependency_overrides[require_authenticated_user] = lambda: {
            "id": str(uuid4()), "email": "citizen@example.com", "role": "user", "email_verified": True,
        }
        assert client.post("/api/collection/admin/staff/invite", json={
            "email": "worker@example.com", "display_name": "Worker", "role": "staff"}).status_code == 403
        app.dependency_overrides.pop(require_authenticated_user)
        app.dependency_overrides[require_admin_user] = lambda: {"id": isolated_grants, "role": "admin"}
        for payload in (
            {"email": "not-an-email", "display_name": "Worker", "role": "staff"},
            {"email": "worker@example.com", "display_name": " ", "role": "staff"},
            {"email": "worker@example.com", "display_name": "Worker", "role": "admin"},
        ):
            assert client.post("/api/collection/admin/staff/invite", json=payload).status_code == 422
    assert called == []


def test_supabase_invitation_is_server_only_and_uses_configured_redirect(monkeypatch):
    invited_id = str(uuid4())
    requests = []
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": invited_id, "email": "worker@example.com"})
    real_client = httpx.AsyncClient
    monkeypatch.setattr(collection.httpx, "AsyncClient", lambda **kwargs: real_client(
        transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr(collection, "get_settings", lambda: Settings(
        _env_file=None, supabase_url="https://project.supabase.co",
        supabase_publishable_key="public-key", supabase_service_role_key="server-secret",
        email_public_base_url="https://sisacare.example"))
    invite = collection.StaffInvite(email="worker@example.com", display_name="Worker", role="staff")
    assert asyncio.run(collection._invite_auth_user(invite))["id"] == invited_id
    request = requests[0]
    assert request.method == "POST" and request.url.path == "/auth/v1/invite"
    assert request.url.params["redirect_to"] == "https://sisacare.example/staff/accept-invite"
    assert request.headers["authorization"] == "Bearer server-secret"
    assert request.headers["apikey"] == "server-secret"
    assert request.read() == b'{"email":"worker@example.com","data":{"full_name":"Worker"}}'


def test_duplicate_auth_account_does_not_create_local_grant(isolated_grants, monkeypatch):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(collection.httpx, "AsyncClient", lambda **kwargs: real_client(
        transport=httpx.MockTransport(lambda _: httpx.Response(422, json={"msg": "duplicate"})), **kwargs))
    monkeypatch.setattr(collection, "get_settings", lambda: Settings(
        _env_file=None, supabase_url="https://project.supabase.co",
        supabase_publishable_key="public-key", supabase_service_role_key="server-secret",
        email_public_base_url="https://sisacare.example"))
    app.dependency_overrides[require_admin_user] = lambda: {"id": isolated_grants, "role": "admin"}
    with TestClient(app) as client:
        response = client.post("/api/collection/admin/staff/invite", json={
            "email": "worker@example.com", "display_name": "Worker", "role": "staff"})
        assert response.status_code == 409
        assert client.get("/api/collection/admin/staff").json() == []


def test_switching_staff_and_driver_keeps_only_one_active_role(isolated_grants):
    user_id = str(uuid4())
    staff.set_grant(user_id, "staff", isolated_grants)
    staff.set_grant(user_id, "driver", isolated_grants)
    with reports._connect() as db:
        active = db.execute("SELECT role FROM role_grants WHERE user_id = ? AND revoked_at IS NULL", (user_id,)).fetchall()
    assert [row["role"] for row in active] == ["driver"]


def test_invite_identity_requires_bearer_and_active_staff_grant(monkeypatch):
    invited_id = str(uuid4())
    tokens = []
    active = True

    async def fake_auth(token, _settings):
        tokens.append(token)
        role = "staff" if active else "user"
        return {"id": invited_id, "email": "worker@example.com", "role": role,
                "email_verified": True}

    monkeypatch.setattr(collection, "authenticate_access_token", fake_auth)
    with pytest.raises(HTTPException) as missing:
        _complete(collection.invited_staff_identity(None))
    assert missing.value.status_code == 401
    assert _complete(collection.invited_staff_identity("Bearer invite-token")) == {
        "user_id": invited_id, "email": "worker@example.com"}
    active = False
    with pytest.raises(HTTPException) as revoked:
        _complete(collection.invited_staff_identity("Bearer invite-token"))
    assert revoked.value.status_code == 403
    assert tokens == ["invite-token", "invite-token"]


def test_resend_requires_active_unverified_grant_and_preserves_auth_uuid(monkeypatch):
    user_id = str(uuid4())
    state = {"grant": {"user_id": user_id, "role": "staff", "invited_at": "2026-11-01",
                       "display_name": "Worker"}, "verified": False}
    sent = []

    async def immediate(func, *args):
        return state["grant"]

    async def auth_user(_user_id):
        return {"id": user_id, "email": "worker@example.com",
                "email_confirmed_at": "2026-11-09" if state["verified"] else None}

    async def send(invite):
        sent.append(invite)
        return {"id": user_id, "email": invite.email}

    monkeypatch.setattr(collection, "run_in_threadpool", immediate)
    monkeypatch.setattr(collection, "_ensure_auth_user", auth_user)
    monkeypatch.setattr(collection, "_invite_auth_user", send)
    admin = {"id": str(uuid4()), "role": "admin"}
    result = _complete(collection.resend_staff_verification(user_id, admin))
    assert result == {"user_id": user_id, "email": "worker@example.com", "verification_email_requested": True}
    assert len(sent) == 1 and sent[0].display_name == "Worker"
    state["verified"] = True
    with pytest.raises(HTTPException) as verified:
        _complete(collection.resend_staff_verification(user_id, admin))
    assert verified.value.status_code == 409
    state["verified"] = False
    state["grant"] = None
    with pytest.raises(HTTPException) as revoked:
        _complete(collection.resend_staff_verification(user_id, admin))
    assert revoked.value.status_code == 404
    assert len(sent) == 1


def test_resend_honors_supabase_cooldown(monkeypatch):
    from datetime import datetime, timezone
    user_id = str(uuid4())

    async def immediate(func, *args):
        return {"role": "driver", "invited_at": "2026-11-01", "display_name": "Driver"}

    async def auth_user(_user_id):
        return {"id": user_id, "email": "driver@example.com", "email_confirmed_at": None,
                "confirmation_sent_at": datetime.now(timezone.utc).isoformat()}

    async def never_send(_invite):
        raise AssertionError("Cooldown must stop the email request.")

    monkeypatch.setattr(collection, "run_in_threadpool", immediate)
    monkeypatch.setattr(collection, "_ensure_auth_user", auth_user)
    monkeypatch.setattr(collection, "_invite_auth_user", never_send)
    with pytest.raises(HTTPException) as recent:
        _complete(collection.resend_staff_verification(user_id, {"id": str(uuid4()), "role": "admin"}))
    assert recent.value.status_code == 429


def test_existing_unverified_staff_gets_signup_confirmation_not_new_invite(monkeypatch):
    user_id = str(uuid4())
    emails = []

    async def immediate(func, *args):
        return {"role": "staff", "invited_at": None, "display_name": "Existing Worker"}

    async def auth_user(_user_id):
        return {"id": user_id, "email": "existing@example.com", "email_confirmed_at": None}

    async def resend_signup(email):
        emails.append(email)

    async def never_invite(_invite):
        raise AssertionError("An existing signup should not get a new invite.")

    monkeypatch.setattr(collection, "run_in_threadpool", immediate)
    monkeypatch.setattr(collection, "_ensure_auth_user", auth_user)
    monkeypatch.setattr(collection, "_resend_signup_confirmation", resend_signup)
    monkeypatch.setattr(collection, "_invite_auth_user", never_invite)
    result = _complete(collection.resend_staff_verification(user_id, {"id": str(uuid4()), "role": "admin"}))
    assert result["verification_email_requested"] is True
    assert emails == ["existing@example.com"]


def test_repeat_invite_rejection_does_not_claim_email_was_sent(monkeypatch):
    user_id = str(uuid4())

    async def immediate(func, *args):
        return {"role": "staff", "invited_at": "2026-11-01", "display_name": "Worker"}

    async def auth_user(_user_id):
        return {"id": user_id, "email": "worker@example.com", "email_confirmed_at": None}

    async def reject(_invite):
        raise HTTPException(409, "Account already exists")

    monkeypatch.setattr(collection, "run_in_threadpool", immediate)
    monkeypatch.setattr(collection, "_ensure_auth_user", auth_user)
    monkeypatch.setattr(collection, "_invite_auth_user", reject)
    with pytest.raises(HTTPException) as rejected:
        _complete(collection.resend_staff_verification(user_id, {"id": str(uuid4()), "role": "admin"}))
    assert rejected.value.status_code == 503
    assert "refused the repeat invitation" in rejected.value.detail


def test_google_verified_email_is_not_marked_unverified():
    assert collection._email_verified({"email": "worker@gmail.com", "email_confirmed_at": None,
        "identities": [{"provider": "google", "identity_data": {
            "email": "worker@gmail.com", "email_verified": True}}]})
    assert not collection._email_verified({"email": "worker@gmail.com", "email_confirmed_at": None,
        "identities": [{"provider": "google", "identity_data": {
            "email": "other@gmail.com", "email_verified": True}}]})
