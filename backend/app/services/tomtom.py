"""Server-side TomTom Search and Reverse Geocoding client."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import Settings


TOMTOM_BASE_URL = "https://api.tomtom.com"


class TomTomError(RuntimeError):
    """Base error for location service failures."""


class TomTomConfigurationError(TomTomError):
    """Raised when the TomTom key is unavailable."""


class TomTomUnavailableError(TomTomError):
    """Raised when TomTom cannot be reached or rejects a request."""


class TomTomInvalidResponseError(TomTomError):
    """Raised when TomTom returns an unexpected response shape."""


def _optional_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _address_payload(address: dict[str, Any]) -> dict[str, str | None]:
    return {
        "address": _optional_string(address.get("freeformAddress")),
        "street": _optional_string(
            address.get("streetNameAndNumber") or address.get("streetName")
        ),
        "city": _optional_string(
            address.get("municipality") or address.get("localName")
        ),
        "state": _optional_string(
            address.get("countrySubdivisionName")
            or address.get("countrySubdivision")
        ),
        "postcode": _optional_string(address.get("postalCode")),
        "country": _optional_string(address.get("country")),
    }


async def _request_json(
    path: str,
    *,
    params: dict[str, object],
    settings: Settings,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    api_key = settings.tomtom_api_key.get_secret_value().strip()
    if not api_key:
        raise TomTomConfigurationError("TomTom location services are not configured.")

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=settings.tomtom_timeout_seconds)
    try:
        try:
            response = await active_client.get(
                f"{TOMTOM_BASE_URL}{path}",
                params={**params, "key": api_key},
                headers={"Accept": "application/json"},
            )
        except httpx.TimeoutException as exc:
            raise TomTomUnavailableError("TomTom location request timed out.") from exc
        except httpx.RequestError as exc:
            raise TomTomUnavailableError(
                "TomTom location services are unavailable."
            ) from exc
    finally:
        if owns_client:
            await active_client.aclose()

    if response.is_error:
        raise TomTomUnavailableError("TomTom location services rejected the request.")
    try:
        payload = response.json()
    except ValueError as exc:
        raise TomTomInvalidResponseError(
            "TomTom returned an unreadable response."
        ) from exc
    if not isinstance(payload, dict):
        raise TomTomInvalidResponseError("TomTom returned an invalid response.")
    return payload


async def search_locations(
    query: str,
    *,
    settings: Settings,
    latitude: float | None = None,
    longitude: float | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, object]]:
    params: dict[str, object] = {
        "typeahead": "true",
        "limit": 6,
        "countrySet": settings.tomtom_country_set,
        "language": "en-MY",
    }
    if latitude is not None and longitude is not None:
        params.update(lat=latitude, lon=longitude)
    payload = await _request_json(
        f"/search/2/search/{quote(query.strip(), safe='')}.json",
        params=params,
        settings=settings,
        client=client,
    )
    results = payload.get("results")
    if not isinstance(results, list):
        raise TomTomInvalidResponseError("TomTom search results are invalid.")

    locations: list[dict[str, object]] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        position = result.get("position")
        address = result.get("address")
        if not isinstance(position, dict) or not isinstance(address, dict):
            continue
        latitude_value = position.get("lat")
        longitude_value = position.get("lon")
        if not isinstance(latitude_value, (int, float)) or not isinstance(
            longitude_value, (int, float)
        ):
            continue
        address_data = _address_payload(address)
        poi = result.get("poi")
        poi_name = (
            _optional_string(poi.get("name")) if isinstance(poi, dict) else None
        )
        address_label = address_data["address"]
        label = address_label or poi_name
        if not label:
            continue
        if poi_name and address_label and poi_name.casefold() not in address_label.casefold():
            label = f"{poi_name}, {address_label}"
        address_data["address"] = label
        locations.append(
            {
                "id": str(result.get("id") or f"{latitude_value},{longitude_value}"),
                "label": label,
                "latitude": float(latitude_value),
                "longitude": float(longitude_value),
                **address_data,
            }
        )
    return locations


async def reverse_geocode(
    latitude: float,
    longitude: float,
    *,
    settings: Settings,
    client: httpx.AsyncClient | None = None,
) -> dict[str, object] | None:
    payload = await _request_json(
        f"/search/2/reverseGeocode/{latitude},{longitude}.json",
        params={"language": "en-MY", "radius": 100},
        settings=settings,
        client=client,
    )
    addresses = payload.get("addresses")
    if not isinstance(addresses, list):
        raise TomTomInvalidResponseError("TomTom reverse-geocoding data is invalid.")
    if not addresses:
        return None
    first = addresses[0]
    if not isinstance(first, dict) or not isinstance(first.get("address"), dict):
        raise TomTomInvalidResponseError("TomTom returned an invalid address.")
    return {
        "latitude": latitude,
        "longitude": longitude,
        **_address_payload(first["address"]),
    }


__all__ = [
    "TomTomConfigurationError",
    "TomTomError",
    "TomTomInvalidResponseError",
    "TomTomUnavailableError",
    "reverse_geocode",
    "search_locations",
]
