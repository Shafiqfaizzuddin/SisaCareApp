from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api import location as location_api
from app.core.config import Settings, get_settings
from app.core.rate_limit import reset_location_rate_limits
from app.main import app
from app.services.tomtom import TomTomConfigurationError


client = TestClient(app)


@pytest.fixture(autouse=True)
def configured_location_api() -> Iterator[None]:
    reset_location_rate_limits()
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        tomtom_api_key="test-key",
    )
    yield
    app.dependency_overrides.clear()
    reset_location_rate_limits()


def test_location_search_returns_service_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search(*_args: object, **_kwargs: object) -> list[dict[str, object]]:
        return [{"id": "one", "label": "UiTM Arau"}]

    monkeypatch.setattr(location_api, "search_locations", fake_search)

    response = client.get("/api/location/search", params={"query": "UiTM Arau"})

    assert response.status_code == 200
    assert response.json() == {"results": [{"id": "one", "label": "UiTM Arau"}]}


def test_reverse_geocode_rejects_invalid_coordinates() -> None:
    response = client.get(
        "/api/location/reverse",
        params={"latitude": 91, "longitude": 100},
    )

    assert response.status_code == 422


def test_missing_tomtom_configuration_is_reported_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_reverse(*_args: object, **_kwargs: object) -> None:
        raise TomTomConfigurationError("TomTom location services are not configured.")

    monkeypatch.setattr(location_api, "reverse_geocode", fail_reverse)

    response = client.get(
        "/api/location/reverse",
        params={"latitude": 6.44, "longitude": 100.27},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "TomTom location services are not configured."


def test_location_api_is_rate_limited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_location_rate_limits()
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        tomtom_api_key="test-key",
        location_rate_limit_requests=1,
    )

    async def fake_search(*_args: object, **_kwargs: object) -> list[object]:
        return []

    monkeypatch.setattr(location_api, "search_locations", fake_search)

    first = client.get("/api/location/search", params={"query": "Arau"})
    second = client.get("/api/location/search", params={"query": "Kangar"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers["retry-after"]
