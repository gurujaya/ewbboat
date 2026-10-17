"""Follow a path (a list of lat/lon points) with pure pursuit. Used by AUTO (the
sweep rows) and by COMING_HOME (the trail home, the backup leg, the way back
inside the fence).

Every step (10 times a second):
  1. where am I along the path? (nav.project_on_path; progress never goes back)
  2. pick the target: the point LOOKAHEAD_M further along the path, moved
     against the current's push as learned so far (see `_drift`)
  3. steer toward it (nav.pursuit_command: P on the heading error, plus a little D)
  4. done when within ARRIVE_M of the last point, or past its end

The math is in nav.py and unit-tested there; this class only keeps the state
between steps (progress, last error) and talks lat/lon to the rest of the boat.
"""

from __future__ import annotations

import config
from nav import LatLon, bearing_deg, direction_at, distance_m, path_lengths, point_at, project_on_path, pursuit_command, to_latlon, to_xy, wrap_deg


class PathFollower:
    def __init__(self, points: list[LatLon], start: LatLon | None = None, label: str = ""):
        """points: the path to follow. start: where the boat is now; if given, the
        path begins there, so the first leg is a straight line to points[0].

        next_index counts in `points` only (not `start`), so AUTO's wp_index matches
        the station's waypoint list."""
        self.points = list(points)
        self.label = label
        self._offset = 1 if start is not None else 0
        path = ([start] if start is not None else []) + self.points
        self.ref: LatLon = path[0] if path else (0.0, 0.0)
        self.xy = [to_xy(p, self.ref) for p in path]
        self.cum = path_lengths(self.xy) if self.xy else [0.0]
        self.s = 0.0                          # progress along the path, m
        self.done = len(self.points) == 0
        self.target: LatLon | None = None     # the point it's steering at, for tlm
        self._err: float | None = None        # last heading error, deg, for the D term
        self._err_rate = 0.0                  # smoothed d(error)/dt, deg/s
        self._t: float | None = None
        # The current's push, learned on the way: how far the boat keeps sitting off the
        # path, east and north (m). The aim point is shifted the other way by this much,
        # so the boat crabs into the current instead of being carried off its row.
        # World frame on purpose: the push is the same on the way out and the way back.
        self._drift: list[float] = [0.0, 0.0]
        self._off: float | None = None        # distance off the path last step, m
        self._steer: float | None = None      # smoothed steering, for STEER_SMOOTH_S
        self._bearing: float | None = None    # smoothed bearing to the aim point, for BEARING_SMOOTH_S

    @property
    def next_index(self) -> int:
        """Index in `points` of the next vertex the boat hasn't passed yet
        (len(points) once done)."""
        if self.done:
            return len(self.points)
        i = 0
        while i < len(self.cum) and self.cum[i] <= self.s:
            i += 1
        return max(0, i - self._offset)

    def step(self, pos: LatLon, heading_deg: float, now: float) -> tuple[float, float, int]:
        """One autopilot step. Returns (left, right, vertices_passed_this_step)."""
        if self.done:
            self.target = None
            return 0.0, 0.0, 0
        before = self.next_index
        p = to_xy(pos, self.ref)
        # Search a little further than the lookahead so a boat pushed ahead of its
        # progress (current, a wide turn) still finds itself on the path.
        self.s, off, past_end = project_on_path(self.xy, self.cum, p, self.s, config.LOOKAHEAD_M * 1.5)
        end = self.points[-1]
        dist_end = distance_m(pos, end)
        # "Close to the last point" only counts near the end of the path: sweep rows
        # are close together, so the last point can be near an early row too.
        near_end_of_path = self.cum[-1] - self.s <= config.LOOKAHEAD_M * 1.5
        # Past the end but still well off it (carried wide by the current): not done; the
        # lookahead clamps to the end point, so the boat turns and comes back to it.
        # Within 1.5x the arrive radius, passing it counts: no orbiting a point it keeps
        # missing by a meter.
        if (dist_end < config.ARRIVE_M and near_end_of_path) or (past_end and dist_end < 1.5 * config.ARRIVE_M):
            self.done = True
            self.target = None
            return 0.0, 0.0, len(self.points) - before

        dt = (now - self._t) if (self._t is not None and now > self._t) else 0.0
        # Learn the push: only while the nose is nearly on target (not mid-turn, and not
        # still closing in on the line from far off), and only a little at a time.
        # Not while the distance off the path is still shrinking fast either: that's the boat
        # closing in on its line, and adding that up would make it overshoot.
        closing = self._off is not None and dt > 0.0 and (off - self._off) / dt < -0.1
        self._off = off
        if dt > 0.0 and self._err is not None and abs(self._err) < 20.0 and not closing:
            here = point_at(self.xy, self.cum, self.s)
            # Only the part of the offset ACROSS the path counts. Along the path the boat can sit
            # behind its recorded progress (a current pushing it along its row, and progress never
            # goes backwards); learning that as a sideways push once wound the aim point 2.7 m
            # behind the boat and sent it into a hard wag.
            (dx, dy), seg_len = direction_at(self.xy, self.cum, self.s)
            ox, oy = p[0] - here[0], p[1] - here[1]
            along = ox * dx + oy * dy
            across = (ox - along * dx, oy - along * dy)
            # ... and only on a stretch long enough to settle on. The short hops between sweep
            # rows are mostly turn, and a push "learned" there can never be corrected on the rows
            # (where across means something else), so it would just pile up.
            if seg_len >= 3.0 * config.LOOKAHEAD_M:
                for k in range(2):
                    self._drift[k] += config.DRIFT_LEARN_PER_S * across[k] * dt
                    self._drift[k] = max(-config.DRIFT_SHIFT_MAX_M, min(config.DRIFT_SHIFT_MAX_M, self._drift[k]))
        if dt > 0.0 and config.DRIFT_FORGET_S > 0.0:
            for k in range(2):
                self._drift[k] -= self._drift[k] * min(1.0, dt / config.DRIFT_FORGET_S)
        ahead = point_at(self.xy, self.cum, self.s + config.LOOKAHEAD_M)
        tgt = to_latlon((ahead[0] - self._drift[0], ahead[1] - self._drift[1]), self.ref)
        self.target = tgt
        bearing = bearing_deg(pos, tgt)
        if config.BEARING_SMOOTH_S > 0.0 and dt > 0.0 and self._bearing is not None and abs(wrap_deg(bearing - self._bearing)) < 30.0:
            self._bearing = (self._bearing + wrap_deg(bearing - self._bearing) * min(1.0, dt / config.BEARING_SMOOTH_S)) % 360.0
        else:
            self._bearing = bearing             # first step, or a real turn: follow it at once
        err = wrap_deg(self._bearing - heading_deg)
        # D term: how fast the error is changing. Heading arrives 5 times a second
        # and this runs 10 times a second, so the raw difference is lumpy (zero,
        # then a jump); a short running average smooths that out.
        if self._err is not None and dt > 0.0:
            raw_rate = wrap_deg(err - self._err) / dt
            self._err_rate += 0.2 * (raw_rate - self._err_rate)
        self._err, self._t = err, now
        # distance left along the path, not straight-line: the trail home can fold back
        left_on_path = max(dist_end, self.cum[-1] - self.s)
        left, right = pursuit_command(
            err, self._err_rate, left_on_path,
            kp=config.KP, kd=config.KD, max_speed=config.MAX_SPEED, slow_radius_m=config.SLOW_RADIUS_M,
        )
        # Smooth the steering (the left/right difference), not the speed. Only on a 1st-order
        # low-pass: a real turn still comes through, the 5 Hz flicker doesn't.
        if config.STEER_SMOOTH_S > 0.0 and dt > 0.0:
            speed, steer = (left + right) / 2.0, (left - right) / 2.0
            if self._steer is None:
                self._steer = steer
            self._steer += (steer - self._steer) * min(1.0, dt / config.STEER_SMOOTH_S)
            left, right = max(-1.0, min(1.0, speed + self._steer)), max(-1.0, min(1.0, speed - self._steer))
        return left, right, self.next_index - before
