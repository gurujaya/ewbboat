"""Run a list of waypoints with nav.go_to_waypoint. Used by AUTO (the sweep) and
by COMING_HOME (the trail, backwards)."""

from __future__ import annotations

import config
from nav import go_to_waypoint


class WaypointRunner:
    def __init__(self, points: list[tuple[float, float]], label: str = ""):
        self.points = list(points)
        self.i = 0
        self.label = label

    @property
    def done(self) -> bool:
        return self.i >= len(self.points)

    @property
    def target(self) -> tuple[float, float] | None:
        return None if self.done else self.points[self.i]

    def step(self, pos: tuple[float, float], heading_deg: float) -> tuple[float, float, bool]:
        """Returns (left, right, reached_a_point_this_step)."""
        if self.done:
            return 0.0, 0.0, False
        left, right, arrived = go_to_waypoint(
            pos, heading_deg, self.points[self.i],
            kp=config.KP, max_speed=config.MAX_SPEED,
            slow_radius_m=config.SLOW_RADIUS_M, arrive_m=config.ARRIVE_M,
        )
        if arrived:
            self.i += 1
            return 0.0, 0.0, True
        return left, right, False
