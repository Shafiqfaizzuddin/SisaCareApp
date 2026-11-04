"""Shared fixed grid for observed density and forecast cells."""
import math

GRID_DEGREES = 0.05


def grid_cell(latitude: float, longitude: float) -> tuple[str, float, float]:
    if not math.isfinite(latitude) or not math.isfinite(longitude) or not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Invalid coordinates")
    lat_index = min(math.floor(latitude / GRID_DEGREES), 1799)
    lon_index = min(math.floor(longitude / GRID_DEGREES), 3599)
    return (f"g005:{lat_index}:{lon_index}",
            round((lat_index + 0.5) * GRID_DEGREES, 6),
            round((lon_index + 0.5) * GRID_DEGREES, 6))
