"""Rectangle -> lawnmower waypoints. Pure math, unit tested."""

from __future__ import annotations

import math

M_PER_DEG_LAT = 111_320.0


def plan(corners: list[tuple[float, float]], row_spacing_m: float, inset_m: float = 2.0) -> list[tuple[float, float]]:
    """Rows run east-west, stepping north. Alternating direction. Insets from the edge
    so the boat's 2 m arrive radius doesn't put it outside the fence."""
    lats = [c[0] for c in corners]
    lons = [c[1] for c in corners]
    lat_min, lat_max, lon_min, lon_max = min(lats), max(lats), min(lons), max(lons)
    lat_mid = (lat_min + lat_max) / 2
    dlat = inset_m / M_PER_DEG_LAT
    dlon = inset_m / (M_PER_DEG_LAT * math.cos(math.radians(lat_mid)))
    lat_min, lat_max = lat_min + dlat, lat_max - dlat
    lon_min, lon_max = lon_min + dlon, lon_max - dlon
    if lat_max <= lat_min or lon_max <= lon_min:
        return []
    step = row_spacing_m / M_PER_DEG_LAT
    n_rows = max(1, int((lat_max - lat_min) / step) + 1)
    pts: list[tuple[float, float]] = []
    for r in range(n_rows):
        lat = min(lat_max, lat_min + r * step)
        a, b = (lon_min, lon_max) if r % 2 == 0 else (lon_max, lon_min)
        pts.append((lat, a))
        pts.append((lat, b))
    return pts
