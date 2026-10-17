"""Breadcrumbs with signal strength. The list the boat can walk backwards.

The points themselves are kept exactly as recorded (they also go to the station).
The paths handed to the autopilot are cleaned-up copies (nav.simplify): GPS
wiggles smoothed out and bunched-up points dropped, so the boat follows the
shape of where it went instead of re-driving every wobble.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from nav import distance_m, simplify


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
    home_settle_s: float = 0.0            # average fixes this long before fixing point 0 (home)
    points: list[TrailPoint] = field(default_factory=list)
    _home_samples: list[tuple[float, float, float, float | None]] = field(default_factory=list)   # (t, lat, lon, dbm)

    @property
    def home(self) -> tuple[float, float] | None:
        """Where the run started. Every trip home ends here."""
        return (self.points[0].lat, self.points[0].lon) if self.points else None

    def maybe_add(self, pos: tuple[float, float], signal_dbm: float | None, now: float | None = None) -> TrailPoint | None:
        """Add a point if we've moved every_m or every_s has passed. Returns it, or None."""
        now = time.time() if now is None else now
        if not self.points:
            return self._settle_home(pos, signal_dbm, now)
        last = self.points[-1]
        moved = distance_m((last.lat, last.lon), pos)
        if moved < self.every_m and now - last.t < self.every_s:
            return None
        p = TrailPoint(len(self.points), pos[0], pos[1], now, signal_dbm)
        self.points.append(p)
        return p

    def _settle_home(self, pos: tuple[float, float], signal_dbm: float | None, now: float) -> TrailPoint | None:
        """Point 0 is home, so it gets more care than the rest: the boat sits at the
        jetty for the first few seconds, and the average of those fixes is a better
        home than whichever single fix came first. If the boat drives off before the
        time is up, use what we have."""
        s = self._home_samples
        s.append((now, pos[0], pos[1], signal_dbm))
        moved = distance_m((s[0][1], s[0][2]), pos)
        if now - s[0][0] < self.home_settle_s and moved < self.every_m:
            return None
        lat = sum(x[1] for x in s) / len(s)
        lon = sum(x[2] for x in s) / len(s)
        dbms = [x[3] for x in s if x[3] is not None]
        p = TrailPoint(0, lat, lon, s[0][0], (sum(dbms) / len(dbms)) if dbms else None)
        self.points.append(p)
        self._home_samples = []
        return p

    def last_good(self, threshold_dbm: float) -> TrailPoint | None:
        """The most recent point where the signal was above threshold."""
        for p in reversed(self.points):
            if p.signal_dbm is not None and p.signal_dbm > threshold_dbm:
                return p
        return self.points[0] if self.points else None

    def path_back_from(self, point: TrailPoint, tolerance_m: float = 1.0, min_gap_m: float = 1.5) -> list[tuple[float, float]]:
        """Path from `point` back to home, walking the trail in reverse (cleaned up)."""
        return simplify([(p.lat, p.lon) for p in reversed(self.points[: point.i + 1])], tolerance_m, min_gap_m)

    def path_back_to(self, point: TrailPoint, tolerance_m: float = 1.0, min_gap_m: float = 1.5) -> list[tuple[float, float]]:
        """Path from the newest point back along the trail to `point` (cleaned up).
        Used to back up to the last spot with good signal by the way we came."""
        return simplify([(p.lat, p.lon) for p in reversed(self.points[point.i :])], tolerance_m, min_gap_m)

    def path_home(self, tolerance_m: float = 1.0, min_gap_m: float = 1.5) -> list[tuple[float, float]]:
        """The whole trail in reverse, newest point to home (cleaned up). Used after a lost
        link; the Come home button goes straight home instead (safety.HomePlan.start_home)."""
        return simplify([(p.lat, p.lon) for p in reversed(self.points)], tolerance_m, min_gap_m)
