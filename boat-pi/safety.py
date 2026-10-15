"""Lost signal, low battery, and the fence. Decides what COMING_HOME is doing.

Lost signal (docs/ARCHITECTURE.md, Level 2):
  WAIT    stop, wait LINK_LOST_WAIT_S. link back -> resume previous mode
  BACKUP  drive to the last trail point with good signal. link back -> resume
  HOME    follow the trail to the launch point
  DONE    stop and wait there

Battery <= 20 %, Come home button: straight to HOME.
Fence exit: FENCE, drive to the nearest inside point, then resume.
"""

from __future__ import annotations

import time
from collections import deque

import config
from autopilot import WaypointRunner
from nav import clamp_to_rect, inside_rect
from trail import Trail


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
    """What COMING_HOME is currently doing."""

    def __init__(self) -> None:
        self.phase = "IDLE"
        self.runner: WaypointRunner | None = None
        self.wait_until = 0.0
        self.reason = ""

    def start_link_lost(self, now: float) -> None:
        self.reason = "link_lost"
        self.phase = "WAIT"
        self.runner = None
        self.wait_until = now + config.LINK_LOST_WAIT_S

    def start_home(self, trail: Trail, reason: str) -> None:
        self.reason = reason
        self.phase = "HOME"
        self.runner = WaypointRunner(trail.path_home(), "home")

    def start_fence(self, pos: tuple[float, float], fence: list[tuple[float, float]]) -> None:
        self.reason = "fence_exit"
        self.phase = "FENCE"
        self.runner = WaypointRunner([clamp_to_rect(pos, fence)], "fence")

    def step(self, pos, heading_deg, trail: Trail, link_up: bool, now: float) -> tuple[float, float, str | None]:
        """Returns (left, right, event) where event is a kind string or None."""
        if self.phase == "WAIT":
            if now >= self.wait_until:
                good = trail.last_good(config.GOOD_SIGNAL_DBM)
                if good is None:
                    self.phase = "DONE"
                    return 0.0, 0.0, "home_done"
                self.phase = "BACKUP"
                self.runner = WaypointRunner([(good.lat, good.lon)], "backup")
                self._backup_point = good
                return 0.0, 0.0, "backing_up"
            return 0.0, 0.0, None

        if self.phase == "BACKUP":
            l, r, reached = self.runner.step(pos, heading_deg)
            if self.runner.done:
                self.phase = "HOME"
                self.runner = WaypointRunner(trail.path_back_from(self._backup_point), "home")
                return 0.0, 0.0, "going_home"
            return l, r, None

        if self.phase in ("HOME", "FENCE"):
            l, r, reached = self.runner.step(pos, heading_deg)
            if self.runner.done:
                was = self.phase
                self.phase = "DONE"
                return 0.0, 0.0, "home_done" if was == "HOME" else "fence_back_inside"
            return l, r, None

        return 0.0, 0.0, None


def fence_ok(pos: tuple[float, float], fence: list[tuple[float, float]] | None) -> bool:
    return fence is None or inside_rect(pos, fence)
