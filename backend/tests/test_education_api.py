from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from app.core.auth import require_authenticated_user
from app.main import app
from app.repositories import reports
from app.api import education as education_api


client = TestClient(app)


@pytest.fixture
def isolated_articles(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(reports, "DATABASE_PATH", tmp_path / "articles.db")
    monkeypatch.setattr(education_api, "_image_dir", lambda: tmp_path / "images")
    yield
    app.dependency_overrides.clear()


def _login(role: str) -> None:
    app.dependency_overrides[require_authenticated_user] = lambda: {
        "id": role, "role": role, "email_verified": True,
    }


def test_public_content_and_admin_editing(isolated_articles) -> None:
    original = client.get("/api/education/articles")
    assert original.status_code == 200
    assert len(original.json()) == 6
    assert client.get("/api/education/articles").json() == original.json()

    _login("user")
    assert client.get("/api/education/admin/articles").status_code == 403
    assert client.post("/api/education/admin/articles", json={
        "title": "No access", "summary": "Summary", "body": "Body",
    }).status_code == 403

    _login("admin")
    payload = {"title": "Sorting waste", "summary": "How to sort it", "body": "Check local acceptance.",
               "image_alt": "", "published": False, "sort_order": 2}
    created = client.post("/api/education/admin/articles", json=payload)
    assert created.status_code == 201
    article_id = created.json()["id"]
    assert article_id not in [item["id"] for item in client.get("/api/education/articles").json()]
    updated = client.put(f"/api/education/admin/articles/{article_id}", json={**payload, "published": True})
    assert updated.status_code == 200
    assert any(item["id"] == article_id for item in client.get("/api/education/articles").json())
    assert client.put("/api/education/admin/articles/missing", json=payload).status_code == 404
    assert client.post("/api/education/admin/articles", json={**payload, "title": "  "}).status_code == 422


def test_image_upload_validation_and_publication(isolated_articles) -> None:
    _login("admin")
    created = client.post("/api/education/admin/articles", json={
        "title": "Recycling", "summary": "Materials", "body": "Check acceptance.",
        "image_alt": "Sorted bottles", "published": False, "sort_order": 0,
    }).json()
    article_id = created["id"]
    picture = BytesIO()
    Image.new("RGB", (64, 40), "green").save(picture, format="PNG")
    result = client.post(f"/api/education/admin/articles/{article_id}/image",
                         files={"image": ("bottles.png", picture.getvalue(), "image/png")})
    assert result.status_code == 200
    assert client.get(f"/api/education/articles/{article_id}/image").status_code == 404
    assert client.get(f"/api/education/admin/articles/{article_id}/image").status_code == 200
    bad = client.post(f"/api/education/admin/articles/{article_id}/image",
                      files={"image": ("bad.png", b"not an image", "image/png")})
    assert bad.status_code == 400
    assert client.get(f"/api/education/admin/articles/{article_id}/image").status_code == 200
    assert client.post(f"/api/education/admin/articles/{article_id}/image/remove").status_code == 200
    assert client.get(f"/api/education/admin/articles/{article_id}/image").status_code == 404
    picture.seek(0)
    assert client.post(f"/api/education/admin/articles/{article_id}/image",
                       files={"image": ("bottles.png", picture.getvalue(), "image/png")}).status_code == 200
    client.put(f"/api/education/admin/articles/{article_id}", json={
        "title": "Recycling", "summary": "Materials", "body": "Check acceptance.",
        "image_alt": "Sorted bottles", "published": True, "sort_order": 0,
    })
    app.dependency_overrides.clear()
    assert client.get(f"/api/education/articles/{article_id}/image").status_code == 200
