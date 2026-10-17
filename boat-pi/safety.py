"""Lost signal, low battery, and the fence. Decides what COMING_HOME is doing.

Lost signal (docs/ARCHITECTURE.md, Level 2):
  WAIT    stop, wait LINK_LOST_WAIT_S. link back -> resume previous mode
  BACKUP  drive back along the trail to the last point with good signal. link back -> resume
  HOME    follow the trail to the launch point
  DONE    stop and wait there

Battery <= 20 %, Come home button: DIRECT, a straight line to the launch point
(the fastest way; the water inside the driving fence is open).
Fence exit: FENCE, drive to a point just inside, then resume (AUTO: the sweep
rectangle; DRIVEN: a circle of DRIVEN_FENCE_M around the station).
"""

from __future__ import annotations

import time
from collections import deque

import config
from autopilot import PathFollower
from nav import inside_circle, inside_rect
from trail import Trail, TrailPoint


class BatteryMonitor:
    """Averages voltage over a few seconds and turns it into a percent.
    The curve is a placeholder until Electrical gives the real pack numbers."""

    V_FULL = 12.6
    V_EMPTY = 10.5

    def __init__(self, avg_s: float):
        self.samples: deque[tuple[float, float]] = deque()
        self.avg_s = avg_s
        self.pct = 100.0
        self.warned = set()

    def update(self, volts: float, now: float | None = None) -> float:
        now = time.time() if now is None else now
        if volts == volts:  # not nan
            self.samples.append((now, volts))
        while self.samples and now - self.samples[0][0] > self.avg_s:
            self.samples.popleft()
        if self.samples:
            v = sum(s[1] for s in self.samples) / len(self.samples)
            self.pct = max(0.0, min(100.0, (v - self.V_EMPTY) / (self.V_FULL - self.V_EMPTY) * 100.0))
        return self.pct

    def crossed(self, threshold: float) -> bool:
        """True once, the first time pct goes at or below threshold."""
        if self.pct <= threshold and threshold not in self.warned:
            self.warned.add(threshold)
            return True
        return False


class HomePlan:
    """What COMING_HOME is currently doing. Every leg is a PathFollower (pure pursuit)."""

    def __init__(self) -> None:
        self.phase = "IDLE"
        self.runner: PathFollower | None = None
        self.wait_until = 0.0
        self.reason = ""
        self._backup_point: TrailPoint | None = None

    @property
    def target(self) -> tuple[float, float] | None:
        """The point the autopilot is steering at right now, or None."""
        if self.phase in ("BACKUP", "HOME", "DIRECT", "FENCE") and self.runner is not None:
            return self.runner.target
        return None

    def start_link_lost(self, now: float) -> None:
        self.reason = "link_lost"
        self.phase = "WAIT"
        self.runner = None
        self.wait_until = now + config.LINK_LOST_WAIT_S

    def start_home(self, trail: Trail, reason: str, pos: tuple[float, float]) -> None:
        """Come home / low battery: the fastest way, a straight line to the launch point.
        (A lost link is different: that retraces the trail, see start_link_lost and step.)"""
        self.reason = reason
        if trail.home is None:
            self.phase = "DONE"             # no fix yet, nowhere to go
            self.runner = None
            return
        self.phase = "DIRECT"
        self.runner = PathFollower([trail.home], start=pos, label="home")

    def start_fence(self, pos: tuple[float, float], inside: tuple[float, float]) -> None:
        """Crossed a fence: go straight to `inside` (a point just inside it)."""
        self.reason = "fence_exit"
        self.phase = "FENCE"
        self.runner = PathFollower([inside], start=pos, label="fence")

    def step(self, pos, heading_deg, trail: Trail, link_up: bool, now: float) -> tuple[float, float, str | None]:
        """Returns (left, right, event) where event is a kind string or None."""
        if self.phase == "WAIT":
            if now >= self.wait_until:
                good = trail.last_good(config.GOOD_SIGNAL_DBM)
                if good is None:
                    self.phase = "DONE"
                    return 0.0, 0.0, "home_done"
                # back up the way we came (the trail is water we know is clear),
                # not in a straight line that might cut across a point of land
                self.phase = "BACKUP"
                self.runner = PathFollower(trail.path_back_to(good, config.TRAIL_SIMPLIFY_M, config.TRAIL_MIN_GAP_M), start=pos, label="backup")
                self._backup_point = good
                return 0.0, 0.0, "backing_up"
            return 0.0, 0.0, None

        if self.phase == "BACKUP":
            l, r, _ = self.runner.step(pos, heading_deg, now)
            if self.runner.done:
                self.phase = "HOME"
                self.runner = PathFollower(trail.path_back_from(self._backup_point, config.TRAIL_SIMPLIFY_M, config.TRAIL_MIN_GAP_M), start=pos, label="home")
                return 0.0, 0.0, "going_home"
            return l, r, None

        if self.phase in ("HOME", "DIRECT", "FENCE"):
            l, r, _ = self.runner.step(pos, heading_deg, now)
            if self.runner.done:
                was = self.phase
                self.phase = "DONE"
                return 0.0, 0.0, "fence_back_inside" if was == "FENCE" else "home_done"
            return l, r, None

        return 0.0, 0.0, None


def fence_ok(pos: tuple[float, float], fence: list[tuple[float, float]] | None) -> bool:
    """AUTO: inside the sweep rectangle (or no rectangle yet)."""
    return fence is None or inside_rect(pos, fence)


def driven_fence_ok(pos: tuple[float, float]) -> bool:
    """DRIVEN: within DRIVEN_FENCE_M of the station."""
    return inside_circle(pos, config.ORIGIN, config.DRIVEN_FENCE_M)
