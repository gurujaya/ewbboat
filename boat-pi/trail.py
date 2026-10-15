"""Breadcrumbs with signal strength. The list the boat can walk backwards."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from nav import distance_m


@dataclass
class TrailPoint:
    i: int
    lat: float
    lon: float
    t: float
    signal_dbm: float | None


@dataclass
class Trail:
    every_m: float
    every_s: float
    points: list[TrailPoint] = field(default_factory=list)

    @property
    def home(self) -> tuple[float, float] | None:
        return (self.points[0].lat, self.points[0].lon) if self.points else None

    def maybe_add(self, pos: tuple[float, float], signal_dbm: float | None, now: float | None = None) -> TrailPoint | None:
        """Add a point if we've moved every_m or every_s has passed. Returns it, or None."""
        now = time.time() if now is None else now
        if self.points:
            last = self.points[-1]
            moved = distance_m((last.lat, last.lon), pos)
            if moved < self.every_m and now - last.t < self.every_s:
                return None
        p = TrailPoint(len(self.points), pos[0], pos[1], now, signal_dbm)
        self.points.append(p)
        return p

    def last_good(self, threshold_dbm: float) -> TrailPoint | None:
        """The most recent point where the signal was above threshold."""
        for p in reversed(self.points):
            if p.signal_dbm is not None and p.signal_dbm > threshold_dbm:
                return p
        return self.points[0] if self.points else None

    def path_back_from(self, point: TrailPoint) -> list[tuple[float, float]]:
        """Waypoints from `point` back to home, walking the trail in reverse."""
        return [(p.lat, p.lon) for p in reversed(self.points[: point.i + 1])]

    def path_home(self) -> list[tuple[float, float]]:
        return [(p.lat, p.lon) for p in reversed(self.points)]
