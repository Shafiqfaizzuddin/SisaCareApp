import asyncio

import httpx
import pytest

from app.core.config import Settings
from app.services.tomtom import (
    TomTomConfigurationError,
    reverse_geocode,
    search_locations,
)


def settings() -> Settings:
    return Settings(_env_file=None, tomtom_api_key="test-key")


def test_search_locations_returns_normalized_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["key"] == "test-key"
        assert request.url.params["countrySet"] == "MY"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "uitm-arau",
                        "position": {"lat": 6.448, "lon": 100.279},
                        "address": {
                            "freeformAddress": "UiTM Arau, Perlis",
                            "municipality": "Arau",
                            "countrySubdivision": "Perlis",
                            "country": "Malaysia",
                        },
                    }
                ]
            },
        )

    async def run_search() -> list[dict[str, object]]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await search_locations(
                "UiTM Arau",
                settings=settings(),
                latitude=6.4,
                longitude=100.2,
                client=client,
            )

    results = asyncio.run(run_search())

    assert results == [
        {
            "id": "uitm-arau",
            "label": "UiTM Arau, Perlis",
            "latitude": 6.448,
            "longitude": 100.279,
            "address": "UiTM Arau, Perlis",
            "street": None,
            "city": "Arau",
            "state": "Perlis",
            "postcode": None,
            "country": "Malaysia",
        }
    ]


def test_reverse_geocode_returns_optional_address_components() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "addresses": [
                    {
                        "address": {
                            "freeformAddress": "Jalan Kangar, Arau",
                            "streetName": "Jalan Kangar",
                            "municipality": "Arau",
                            "country": "Malaysia",
                        }
                    }
                ]
            },
        )

    async def run_reverse() -> dict[str, object] | None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await reverse_geocode(
                6.44,
                100.27,
                settings=settings(),
                client=client,
            )

    result = asyncio.run(run_reverse())

    assert result is not None
    assert result["address"] == "Jalan Kangar, Arau"
    assert result["street"] == "Jalan Kangar"
    assert result["postcode"] is None


def test_missing_tomtom_key_is_a_configuration_error() -> None:
    async def run_reverse() -> None:
        await reverse_geocode(
            6.44,
            100.27,
            settings=Settings(_env_file=None),
        )

    with pytest.raises(TomTomConfigurationError):
        asyncio.run(run_reverse())
