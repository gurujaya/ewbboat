"""The boat is always in exactly one mode. This is the only file that changes it.

Allowed transitions are the table at the bottom of docs/MESSAGES.md. Safety
code calls `request(...)` with a reason; this file says yes or no.
"""

from __future__ import annotations

from dataclasses import dataclass

DRIVEN, AUTO, COMING_HOME = "DRIVEN", "AUTO", "COMING_HOME"

# who may ask for what
OPERATOR_REASONS = {"take_control", "start_sweep", "come_home"}
SAFETY_REASONS = {"link_lost", "batt_low", "fence_exit"}


@dataclass
class ModeChange:
    ok: bool
    mode: str
    msg: str = ""


class Modes:
    def __init__(self) -> None:
        self.mode = DRIVEN
        self.previous = DRIVEN
        self.reason = ""

    def request(self, want: str, reason: str, *, link_up: bool, batt_pct: float, have_waypoints: bool = False, gps_fix: bool = True) -> ModeChange:
        cur = self.mode

        if reason in SAFETY_REASONS:
            # safety always wins and always lands in COMING_HOME
            return self._set(COMING_HOME, reason)

        if reason not in OPERATOR_REASONS:
            return ModeChange(False, cur, f"unknown reason {reason}")

        if not link_up:
            return ModeChange(False, cur, "no link; operator requests ignored")

        if want == AUTO:
            if cur == COMING_HOME:
                return ModeChange(False, cur, "go through DRIVEN first")
            if batt_pct <= 30:
                return ModeChange(False, cur, "battery at or below 30 %")
            if not gps_fix:
                return ModeChange(False, cur, "no GPS fix")
            if not have_waypoints:
                return ModeChange(False, cur, "no waypoint list")
            return self._set(AUTO, reason)

        if want == DRIVEN:
            if cur == COMING_HOME and batt_pct <= 20:
                return ModeChange(False, cur, "battery at or below 20 %, staying in COMING_HOME")
            return self._set(DRIVEN, reason)

        if want == COMING_HOME:
            return self._set(COMING_HOME, reason)

        return ModeChange(False, cur, f"unknown mode {want}")

    def resume_previous(self) -> ModeChange:
        """Link came back during a link-lost COMING_HOME: carry on as before."""
        if self.mode == COMING_HOME and self.reason == "link_lost":
            prev = self.previous if self.previous != COMING_HOME else DRIVEN
            return self._set(prev, "link_back")
        return ModeChange(False, self.mode, "nothing to resume")

    def _set(self, mode: str, reason: str) -> ModeChange:
        if mode != self.mode:
            self.previous = self.mode
        self.mode = mode
        self.reason = reason
        return ModeChange(True, mode, reason)
