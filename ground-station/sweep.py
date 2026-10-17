"""Rectangle -> lawnmower waypoints. Pure math, unit tested."""

from __future__ import annotations

import math

M_PER_DEG_LAT = 111_320.0


def corners_inside_circle(corners: list[tuple[float, float]], center: tuple[float, float], radius_m: float) -> bool:
    """All four corners of the rectangle within radius_m of center (flat earth, fine for a pond).
    A sweep drawn past the driving fence would send the boat out of radio range on purpose."""
    cos = math.cos(math.radians(center[0]))
    lats = [c[0] for c in corners]
    lons = [c[1] for c in corners]
    for lat in (min(lats), max(lats)):
        for lon in (min(lons), max(lons)):
            dx = (lon - center[1]) * M_PER_DEG_LAT * cos
            dy = (lat - center[0]) * M_PER_DEG_LAT
            if math.hypot(dx, dy) > radius_m:
                return False
    return True


def plan(corners: list[tuple[float, float]], row_spacing_m: float, inset_m: float = 2.0, turn_rows: int = 1) -> list[tuple[float, float]]:
    """Rows run east-west, stepping north. Alternating direction. Insets from the edge
    so the boat's 2 m arrive radius doesn't put it outside the fence.

    turn_rows: how many rows apart consecutive rows are. 1 = plain lawnmower (U-turn
    into the next row). With rows only a boat-width apart the U-turn is tighter than
    the boat can make, so 2 does every other row first (0, 2, 4, ...) and then comes
    back for the ones in between (1, 3, 5, ...): each turn spans two row gaps."""
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
    n_rows = max(1, int((lat_max - lat_min) / step + 1e-9) + 1)   # 1e-9: 16/4 must give 5 rows, not 4
    order = [r for k in range(max(1, turn_rows)) for r in range(k, n_rows, max(1, turn_rows))]
    pts: list[tuple[float, float]] = []
    for i, r in enumerate(order):
        lat = min(lat_max, lat_min + r * step)
        a, b = (lon_min, lon_max) if i % 2 == 0 else (lon_max, lon_min)   # alternate in visiting order
        pts.append((lat, a))
        pts.append((lat, b))
    return pts
