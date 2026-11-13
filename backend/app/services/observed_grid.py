"""Stable 1 km Web Mercator cells for administrative observed-report counts.

The cell size is in projected metres; ground distance differs slightly by
latitude. Forecasts deliberately retain their separate 0.05-degree grid.
"""
import math

CELL_METERS = 1000
EARTH_RADIUS_METERS = 6378137
MAX_LATITUDE = 85.05112878
MAX_INDEX = 20037


def observed_cell(latitude: float, longitude: float) -> tuple[str, float, float, float, float, float, float]:
    if (not math.isfinite(latitude) or not math.isfinite(longitude)
            or abs(latitude) > MAX_LATITUDE or not -180 <= longitude <= 180):
        raise ValueError("Invalid map coordinates")
    x = EARTH_RADIUS_METERS * math.radians(longitude)
    y = EARTH_RADIUS_METERS * math.log(math.tan(math.pi / 4 + math.radians(latitude) / 2))
    x_index = min(math.floor(x / CELL_METERS), MAX_INDEX)
    y_index = min(math.floor(y / CELL_METERS), MAX_INDEX)

    def lat_at(metres: float) -> float:
        return math.degrees(math.atan(math.sinh(metres / EARTH_RADIUS_METERS)))

    west = max(-180, math.degrees(x_index * CELL_METERS / EARTH_RADIUS_METERS))
    east = min(180, math.degrees((x_index + 1) * CELL_METERS / EARTH_RADIUS_METERS))
    south = lat_at(y_index * CELL_METERS)
    north = lat_at((y_index + 1) * CELL_METERS)
    return (f"g1km:{x_index}:{y_index}", (south + north) / 2,
            (west + east) / 2, south, north, west, east)
