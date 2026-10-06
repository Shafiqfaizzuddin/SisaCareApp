"""TomTom-backed location search and reverse-geocoding endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.config import Settings, get_settings
from app.core.rate_limit import enforce_location_rate_limit
from app.services.tomtom import (
    TomTomConfigurationError,
    TomTomInvalidResponseError,
    TomTomUnavailableError,
    reverse_geocode,
    search_locations,
)


router = APIRouter(dependencies=[Depends(enforce_location_rate_limit)])


def _service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, TomTomConfigurationError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, TomTomInvalidResponseError):
        return HTTPException(
            status_code=502,
            detail="TomTom returned an invalid location response.",
        )
    return HTTPException(
        status_code=502,
        detail="TomTom location services are temporarily unavailable.",
    )


@router.get("/search")
async def search_location(
    query: Annotated[str, Query(min_length=3, max_length=100)],
    settings: Annotated[Settings, Depends(get_settings)],
    latitude: Annotated[float | None, Query(ge=-90, le=90)] = None,
    longitude: Annotated[float | None, Query(ge=-180, le=180)] = None,
) -> dict[str, object]:
    if (latitude is None) != (longitude is None):
        raise HTTPException(
            status_code=422,
            detail="Latitude and longitude must be supplied together.",
        )
    try:
        results = await search_locations(
            query,
            settings=settings,
            latitude=latitude,
            longitude=longitude,
        )
    except (TomTomConfigurationError, TomTomInvalidResponseError, TomTomUnavailableError) as exc:
        raise _service_error(exc) from exc
    return {"results": results}


@router.get("/reverse")
async def read_reverse_geocode(
    latitude: Annotated[float, Query(ge=-90, le=90)],
    longitude: Annotated[float, Query(ge=-180, le=180)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    try:
        location = await reverse_geocode(
            latitude,
            longitude,
            settings=settings,
        )
    except (TomTomConfigurationError, TomTomInvalidResponseError, TomTomUnavailableError) as exc:
        raise _service_error(exc) from exc
    if location is None:
        raise HTTPException(
            status_code=404,
            detail="No readable address was found for these coordinates.",
        )
    return location


__all__ = ["router"]
