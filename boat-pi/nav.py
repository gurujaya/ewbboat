"""Algorithm 1: get to one waypoint. Pure math, no hardware, fully unit-tested.

Headings and bearings are degrees, 0-360, clockwise from north (0 = north,
90 = east). Positions are (lat, lon) in decimal degrees. Distances in meters.
"""

from __future__ import annotations

import math

EARTH_M_PER_DEG_LAT = 111_320.0


def wrap_deg(d: float) -> float:
    """Wrap any angle to (-180, 180]. wrap(350) = -10, wrap(-190) = 170."""
    d = (d + 180.0) % 360.0 - 180.0
    return 180.0 if d == -180.0 else d


def distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Flat-earth distance. Fine for a pond; wrong across an ocean."""
    dlat = (b[0] - a[0]) * EARTH_M_PER_DEG_LAT
    dlon = (b[1] - a[1]) * EARTH_M_PER_DEG_LAT * math.cos(math.radians(a[0]))
    return math.hypot(dlat, dlon)


def bearing_deg(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Direction from a to b, 0-360 clockwise from north."""
    dlat = b[0] - a[0]
    dlon = (b[1] - a[1]) * math.cos(math.radians(a[0]))
    return math.degrees(math.atan2(dlon, dlat)) % 360.0


def go_to_waypoint(
    pos: tuple[float, float],
    heading_deg: float,
    target: tuple[float, float],
    kp: float,
    max_speed: float,
    slow_radius_m: float,
    arrive_m: float,
) -> tuple[float, float, bool]:
    """One step of the autopilot. Returns (left, right, arrived).

    error  = how far the nose is from pointing at the target
    steer  = a fraction of that error
    speed  = full up to slow_radius, then eases off
    """
    dist = distance_m(pos, target)
    error = wrap_deg(bearing_deg(pos, target) - heading_deg)
    # arrived: inside the radius, or we just drove past it (it's close and behind us).
    # the second rule stops the boat orbiting a point it keeps missing by a meter.
    if dist < arrive_m or (dist < 2.5 * arrive_m and abs(error) > 100):
        return 0.0, 0.0, True
    steer = max(-0.6, min(0.6, kp * error))
    speed = max_speed * min(1.0, dist / slow_radius_m)
    # if we're pointing way off, turn more than we drive
    if abs(error) > 60:
        speed *= 0.3
    left = max(-1.0, min(1.0, speed + steer))
    right = max(-1.0, min(1.0, speed - steer))
    return left, right, False


def mix(throttle: float, steer: float) -> tuple[float, float]:
    """Gamepad -> motors. Same formula the autopilot uses, so both paths behave alike."""
    left = max(-1.0, min(1.0, throttle + steer))
    right = max(-1.0, min(1.0, throttle - steer))
    return left, right


def inside_rect(pos: tuple[float, float], corners: list[tuple[float, float]]) -> bool:
    """Is pos inside the lat/lon bounding box of the corners?"""
    lats = [c[0] for c in corners]
    lons = [c[1] for c in corners]
    return min(lats) <= pos[0] <= max(lats) and min(lons) <= pos[1] <= max(lons)


def clamp_to_rect(pos: tuple[float, float], corners: list[tuple[float, float]], margin_m: float = 3.0) -> tuple[float, float]:
    """Nearest point inside the box, pulled `margin_m` in from the edge."""
    lats = [c[0] for c in corners]
    lons = [c[1] for c in corners]
    mlat = margin_m / EARTH_M_PER_DEG_LAT
    mlon = margin_m / (EARTH_M_PER_DEG_LAT * math.cos(math.radians(pos[0])))
    lat = max(min(lats) + mlat, min(pos[0], max(lats) - mlat))
    lon = max(min(lons) + mlon, min(pos[1], max(lons) - mlon))
    return lat, lon
