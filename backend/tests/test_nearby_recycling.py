import asyncio

import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr
import pytest

from app.api import location as location_api
from app.core.auth import require_authenticated_user
from app.core.config import Settings, get_settings
from app.main import app
from app.services.tomtom import search_nearby_recycling


def test_tomtom_recycling_search_uses_selected_area_and_preserves_unknown_materials() -> None:
    requests: list[httpx.Request] = []
    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": [{
            "id": "poi-1", "position": {"lat": 6.8, "lon": 100.3},
            "poi": {"name": "Recycling Centre"}, "address": {"freeformAddress": "Test Road"},
        }]})
    settings = Settings(_env_file=None, tomtom_api_key=SecretStr("test-key"))
    async def search() -> list[dict[str, object]]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await search_nearby_recycling(6.8, 100.3, settings=settings, client=client)
    result = asyncio.run(search())
    assert result[0]["accepted_materials"] is None
    assert result[0]["address"] == "Test Road"
    assert "/categorySearch/recycling.json" in requests[0].url.path
    assert requests[0].url.params["lat"] == "6.8"
    assert requests[0].url.params["lon"] == "100.3"
    assert requests[0].url.params["radius"] == "20000"


def test_nearby_endpoint_accepts_outside_campus_and_validates_coordinates(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[tuple[float, float]] = []
    async def search(latitude: float, longitude: float, *, settings: Settings) -> list[dict[str, object]]:
        called.append((latitude, longitude))
        return []
    monkeypatch.setattr(location_api, "search_nearby_recycling", search)
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    app.dependency_overrides[require_authenticated_user] = lambda: {"id": "participant", "role": "user"}
    try:
        client = TestClient(app)
        response = client.get("/api/location/recycling/nearby", params={"latitude": 6.8, "longitude": 100.3})
        assert response.status_code == 200
        assert response.json() == {"results": []}
        assert called == [(6.8, 100.3)]
        assert client.get("/api/location/recycling/nearby", params={"latitude": 91, "longitude": 100.3}).status_code == 422
        del app.dependency_overrides[require_authenticated_user]
        assert client.get("/api/location/recycling/nearby", params={"latitude": 6.8, "longitude": 100.3}).status_code == 401
    finally:
        app.dependency_overrides.clear()
