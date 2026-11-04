from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import FrontendFiles


def test_frontend_files_serve_spa_without_masking_missing_api_or_assets(tmp_path):
    (tmp_path / "index.html").write_text("<main>SisaCare</main>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('ready')", encoding="utf-8")

    app = FastAPI()
    app.mount("/", FrontendFiles(directory=tmp_path, html=True))
    client = TestClient(app)

    assert client.get("/").text == "<main>SisaCare</main>"
    assert client.get("/account/reports/example").text == "<main>SisaCare</main>"
    assert client.get("/assets/app.js").text == "console.log('ready')"
    assert client.get("/assets/missing.js").status_code == 404
    assert client.get("/api/missing").status_code == 404
