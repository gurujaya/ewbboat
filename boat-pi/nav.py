"""Navigation math. Pure functions and one small filter: no hardware, no clock,
fully unit-tested (tests/test_nav.py).

Headings and bearings are degrees, 0-360, clockwise from north (0 = north,
90 = east). Positions are (lat, lon) in decimal degrees. Distances in meters.

For anything geometric (the position filter, following a path, simplifying the
trail) we first turn lat/lon into a flat local frame in meters: x east, y north,
measured from a reference point. Over a pond the earth is flat to well under a
centimeter, and meters are much easier to think about than degrees.

What's here:
  - basics: wrap_deg, distance_m, bearing_deg, mix, to_xy / to_latlon
  - PositionFilter: smooths GPS fixes and predicts between them (speed, course)
  - path following (pure pursuit): path_lengths, project_on_path, point_at,
    pursuit_command. autopilot.PathFollower wires these together.
  - simplify: cleans up the trail before the boat follows it home
  - fences: inside_rect / clamp_to_rect (sweep), inside_circle / point_inside_circle (driving)
"""

from __future__ import annotations

import math

EARTH_M_PER_DEG_LAT = 111_320.0

XY = tuple[float, float]       # meters east, north of some reference point
LatLon = tuple[float, float]   # decimal degrees


# ---- basics -------------------------------------------------------------------


def wrap_deg(d: float) -> float:
    """Wrap any angle to (-180, 180]. wrap(350) = -10, wrap(-190) = 170."""
    d = (d + 180.0) % 360.0 - 180.0
    return 180.0 if d == -180.0 else d


def distance_m(a: LatLon, b: LatLon) -> float:
    """Flat-earth distance. Fine for a pond; wrong across an ocean."""
    dlat = (b[0] - a[0]) * EARTH_M_PER_DEG_LAT
    dlon = (b[1] - a[1]) * EARTH_M_PER_DEG_LAT * math.cos(math.radians(a[0]))
    return math.hypot(dlat, dlon)


def bearing_deg(a: LatLon, b: LatLon) -> float:
    """Direction from a to b, 0-360 clockwise from north."""
    dlat = b[0] - a[0]
    dlon = (b[1] - a[1]) * math.cos(math.radians(a[0]))
    return math.degrees(math.atan2(dlon, dlat)) % 360.0


def to_xy(p: LatLon, ref: LatLon) -> XY:
    """lat/lon -> meters (east, north) of ref."""
    x = (p[1] - ref[1]) * EARTH_M_PER_DEG_LAT * math.cos(math.radians(ref[0]))
    y = (p[0] - ref[0]) * EARTH_M_PER_DEG_LAT
    return x, y


def to_latlon(xy: XY, ref: LatLon) -> LatLon:
    """The reverse of to_xy."""
    lat = ref[0] + xy[1] / EARTH_M_PER_DEG_LAT
    lon = ref[1] + xy[0] / (EARTH_M_PER_DEG_LAT * math.cos(math.radians(ref[0])))
    return lat, lon


def heading_of(dx: float, dy: float) -> float:
    """Direction of the vector (east dx, north dy), 0-360 clockwise from north."""
    return math.degrees(math.atan2(dx, dy)) % 360.0


def smooth_heading(prev: float | None, new_deg: float, dt: float, tau_s: float) -> float:
    """Low-pass a compass heading. Goes the short way round (359 -> 1 is a 2 degree
    step, not 358). tau_s = 0 means no smoothing. A compass on a small boat near two
    motors jitters a couple of degrees reading to reading; steering on that jitter
    makes the boat wag its nose."""
    if prev is None or tau_s <= 0.0 or dt <= 0.0:
        return new_deg % 360.0
    k = min(1.0, dt / tau_s)
    return (prev + wrap_deg(new_deg - prev) * k) % 360.0


def mix(throttle: float, steer: float) -> tuple[float, float]:
    """Gamepad -> motors. Same formula the autopilot uses, so both paths behave alike."""
    left = max(-1.0, min(1.0, throttle + steer))
    right = max(-1.0, min(1.0, throttle - steer))
    return left, right


# ---- position filter ------------------------------------------------------------


class PositionFilter:
    """Smooths GPS fixes and predicts where the boat is between them.

    Why: a raw GPS fix jumps around by a meter or so from one reading to the
    next. Steering on raw fixes makes the autopilot chase that jitter (zig-zag),
    and the dashboard's boat hops. The filter keeps a position and a velocity
    and nudges them toward each new fix instead of jumping to it.

    Why alpha-beta and not a Kalman filter: our fixes arrive at a steady 5 Hz
    with roughly constant noise. In that situation a constant-velocity Kalman
    filter's gains settle to two fixed numbers after a few seconds anyway; an
    alpha-beta filter just writes those two numbers down. Same result, no
    matrices, and anyone can follow it:

        predict:  pos = pos + vel * dt                 (assume steady speed)
        compare:  miss = fix - pos                     (how far off the guess was)
        correct:  pos = pos + alpha * miss             (believe the fix a bit)
                  vel = vel + beta / dt * miss         (and adjust the speed)

    alpha near 1 trusts the GPS (jumpy), near 0 trusts the prediction (laggy).
    It runs separately on east and north, in meters from the first fix.

    What it can't do: real GPS error also drifts slowly (a meter or two over
    tens of seconds). No filter can tell that drift from real movement; only a
    better GPS (RTK) fixes it. The filter removes the fast jitter.
    """

    def __init__(self, alpha: float = 0.4, beta: float = 0.1, gap_reset_s: float = 2.0, jump_m: float = 15.0, max_predict_s: float = 1.0):
        self.alpha = alpha
        self.beta = beta
        self.gap_reset_s = gap_reset_s        # no fix for this long: start over (velocity is stale)
        self.jump_m = jump_m                  # a fix this far from the prediction is a glitch...
        self.max_predict_s = max_predict_s    # never extrapolate further than this past the last fix
        self.ref: LatLon | None = None        # the local frame's zero
        self.reset()

    def reset(self) -> None:
        """Forget everything. Call when the GPS loses its fix."""
        self.x = self.y = 0.0                 # m east, north of ref
        self.vx = self.vy = 0.0               # m/s
        self.t_last: float | None = None      # time of the last fix used
        self.t_first: float | None = None     # time of the first fix since the reset
        self.last_fix: LatLon | None = None
        self.jumps = 0                        # glitches in a row

    @property
    def ready(self) -> bool:
        return self.t_last is not None

    def update(self, t: float, fix: LatLon) -> None:
        """Feed one GPS fix taken at time t (seconds)."""
        if fix == self.last_fix:
            # Same numbers as last time: the GPS hasn't made a new fix yet and the
            # Arduino repeated the old one. Counting it twice would look like the
            # boat had stopped.
            return
        if self.ref is None:
            self.ref = fix
        zx, zy = to_xy(fix, self.ref)
        if self.t_last is None or t - self.t_last > self.gap_reset_s:
            self._start(t, fix, zx, zy)
            return
        dt = t - self.t_last
        if dt <= 0.0:
            return
        px, py = self.x + self.vx * dt, self.y + self.vy * dt
        mx, my = zx - px, zy - py
        if math.hypot(mx, my) > self.jump_m:
            # ...unless it keeps happening: then the GPS really is somewhere else
            # (it just re-acquired, or we were wrong). Start over from the new fix.
            self.jumps += 1
            if self.jumps >= 3:
                self._start(t, fix, zx, zy)
            return
        self.jumps = 0
        self.x, self.y = px + self.alpha * mx, py + self.alpha * my
        self.vx += self.beta / dt * mx
        self.vy += self.beta / dt * my
        self.t_last = t
        self.last_fix = fix

    def _start(self, t: float, fix: LatLon, zx: float, zy: float) -> None:
        self.reset()
        self.x, self.y = zx, zy
        self.t_last = self.t_first = t
        self.last_fix = fix

    def position(self, now: float) -> LatLon | None:
        """Best guess of where the boat is at `now`, or None before the first fix."""
        if self.t_last is None or self.ref is None:
            return None
        dt = max(0.0, min(self.max_predict_s, now - self.t_last))
        return to_latlon((self.x + self.vx * dt, self.y + self.vy * dt), self.ref)

    def speed_mps(self) -> float | None:
        """Speed over ground. None until there's at least a second of fixes, because
        until then the velocity is still mostly a guess."""
        if self.t_last is None or self.t_first is None or self.t_last - self.t_first < 1.0:
            return None
        return math.hypot(self.vx, self.vy)

    def course_deg(self, min_speed_mps: float = 0.3) -> float | None:
        """Direction of travel over ground (not where the nose points: current pushes
        the boat sideways). None when too slow for the direction to mean anything."""
        s = self.speed_mps()
        if s is None or s < min_speed_mps:
            return None
        return heading_of(self.vx, self.vy)


# ---- path following (pure pursuit) -------------------------------------------------
#
# The boat follows a polyline (the sweep rows, or the trail home) the way a
# person drives a car along a road: look a few meters down the road and steer
# toward that spot. It never has to "arrive" at each corner, so it doesn't slow
# down at every point, and it naturally cuts back to the line after a push from
# the current. "Progress" is how many meters along the path the boat has got.


def path_lengths(path: list[XY]) -> list[float]:
    """Cumulative length at each vertex: [0, len(seg0), len(seg0)+len(seg1), ...]."""
    out = [0.0]
    for a, b in zip(path, path[1:]):
        out.append(out[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    return out


def project_on_path(path: list[XY], cum: list[float], pos: XY, s_from: float, window_m: float) -> tuple[float, float, bool]:
    """Where is pos along the path? Returns (progress_m, distance_from_path_m, past_end).

    Only looks between s_from and s_from + window_m, and never returns less than
    s_from: progress never goes backwards. That matters where the path folds back
    on itself (sweep rows 3 m apart, or the trail home retracing a sweep): the
    closest bit of path might be a row we already did, or one we haven't reached.

    past_end is True when the boat is beyond the end of the last segment (it
    overshot the final point, so there's nothing left to follow).
    """
    best_s, best_d = s_from, float("inf")
    s_to = s_from + window_m
    for i in range(len(path) - 1):
        if cum[i + 1] < s_from or cum[i] > s_to:
            continue
        (ax, ay), (bx, by) = path[i], path[i + 1]
        seg = cum[i + 1] - cum[i]
        if seg <= 0.0:
            continue
        ux, uy = (bx - ax) / seg, (by - ay) / seg
        along = (pos[0] - ax) * ux + (pos[1] - ay) * uy
        # clamp to this segment, and to the window
        s = max(s_from, min(s_to, cum[i] + max(0.0, min(seg, along))))
        f = max(0.0, min(seg, s - cum[i]))
        d = math.hypot(pos[0] - (ax + f * ux), pos[1] - (ay + f * uy))
        if d < best_d:
            best_s, best_d = s, d
    # beyond the end: project onto the last segment without clamping
    past_end = False
    if len(path) >= 2 and best_s >= cum[-2]:
        (ax, ay), (bx, by) = path[-2], path[-1]
        seg = cum[-1] - cum[-2]
        if seg > 0.0:
            along = ((pos[0] - ax) * (bx - ax) + (pos[1] - ay) * (by - ay)) / seg
            past_end = along > seg
    return best_s, best_d, past_end


def direction_at(path: list[XY], cum: list[float], s: float) -> tuple[XY, float]:
    """The path at s meters: (unit vector along it, length of that segment)."""
    if len(path) < 2:
        return (0.0, 1.0), 0.0
    i = 0
    while i < len(path) - 2 and cum[i + 1] <= s:
        i += 1
    (ax, ay), (bx, by) = path[i], path[i + 1]
    seg = math.hypot(bx - ax, by - ay)
    return (((bx - ax) / seg, (by - ay) / seg) if seg > 0.0 else (0.0, 1.0)), seg


def point_at(path: list[XY], cum: list[float], s: float) -> XY:
    """The point s meters along the path (clamped to its ends)."""
    if s <= 0.0 or len(path) == 1:
        return path[0]
    if s >= cum[-1]:
        return path[-1]
    for i in range(len(path) - 1):
        if cum[i + 1] >= s:
            seg = cum[i + 1] - cum[i]
            f = 0.0 if seg <= 0.0 else (s - cum[i]) / seg
            (ax, ay), (bx, by) = path[i], path[i + 1]
            return ax + f * (bx - ax), ay + f * (by - ay)
    return path[-1]


def pursuit_command(
    error_deg: float,
    error_rate_dps: float,
    dist_to_end_m: float,
    kp: float,
    kd: float,
    max_speed: float,
    slow_radius_m: float,
    max_steer: float = 0.6,
    min_speed_frac: float = 0.3,
) -> tuple[float, float]:
    """Heading error to the target point -> (left, right).

    error_deg       how far the nose is from pointing at the target, -180..180 (+ = target is to the right)
    error_rate_dps  how fast that error is changing; the D term damps the swing so it doesn't overshoot
    dist_to_end_m   meters left to the FINAL point of the path (not the target point)

    steer = kp * error + kd * error_rate
    speed = cruise, but ease off within slow_radius_m of the end, and when the
            nose is far off (turn first, then drive; also makes U-turns tighter)
    """
    steer = max(-max_steer, min(max_steer, kp * error_deg + kd * error_rate_dps))
    speed = max_speed * max(min_speed_frac, min(1.0, dist_to_end_m / slow_radius_m))
    # full speed up to 20 degrees off, down to 30 % at 80 degrees or more
    off = abs(error_deg)
    speed *= max(0.3, min(1.0, 1.0 - (off - 20.0) / 60.0 * 0.7))
    return mix(speed, steer)


# ---- trail clean-up ------------------------------------------------------------------


def simplify(points: list[LatLon], tolerance_m: float, min_gap_m: float = 1.5) -> list[LatLon]:
    """A cleaner copy of a path, with the same shape. The first and last points are kept.

    1. Drop points closer than min_gap_m to the previous kept one (a boat that
       sat still for a minute leaves a little heap of points).
    2. Douglas-Peucker: keep the end points, find the point furthest from the
       straight line between them; if it's within tolerance_m, the whole stretch
       is "basically straight" and the middle points go. Otherwise keep that
       point and do the same on both halves. Small GPS wiggles disappear, real
       corners stay.
    """
    if len(points) <= 2:
        return list(points)
    ref = points[0]
    kept = [points[0]]
    for p in points[1:-1]:
        if distance_m(kept[-1], p) >= min_gap_m:
            kept.append(p)
    if distance_m(kept[-1], points[-1]) < min_gap_m and len(kept) > 1:
        kept.pop()             # keep the true end point rather than the one just before it
    kept.append(points[-1])

    xy = [to_xy(p, ref) for p in kept]
    keep = [False] * len(xy)
    keep[0] = keep[-1] = True
    stack = [(0, len(xy) - 1)]
    while stack:
        i, j = stack.pop()
        (ax, ay), (bx, by) = xy[i], xy[j]
        far_k, far_d = -1, -1.0
        for k in range(i + 1, j):
            d = _dist_to_segment(xy[k], (ax, ay), (bx, by))
            if d > far_d:
                far_k, far_d = k, d
        if far_k >= 0 and far_d > tolerance_m:
            keep[far_k] = True
            stack.append((i, far_k))
            stack.append((far_k, j))
    return [p for p, k in zip(kept, keep) if k]


def _dist_to_segment(p: XY, a: XY, b: XY) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 == 0.0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    f = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.hypot(p[0] - (a[0] + f * dx), p[1] - (a[1] + f * dy))


# ---- fences -----------------------------------------------------------------------------


def inside_rect(pos: LatLon, corners: list[LatLon]) -> bool:
    """Is pos inside the lat/lon bounding box of the corners?"""
    lats = [c[0] for c in corners]
    lons = [c[1] for c in corners]
    return min(lats) <= pos[0] <= max(lats) and min(lons) <= pos[1] <= max(lons)


def clamp_to_rect(pos: LatLon, corners: list[LatLon], margin_m: float = 3.0) -> LatLon:
    """Nearest point inside the box, pulled `margin_m` in from the edge."""
    lats = [c[0] for c in corners]
    lons = [c[1] for c in corners]
    mlat = margin_m / EARTH_M_PER_DEG_LAT
    mlon = margin_m / (EARTH_M_PER_DEG_LAT * math.cos(math.radians(pos[0])))
    lat = max(min(lats) + mlat, min(pos[0], max(lats) - mlat))
    lon = max(min(lons) + mlon, min(pos[1], max(lons) - mlon))
    return lat, lon


def inside_circle(pos: LatLon, center: LatLon, radius_m: float) -> bool:
    """The driving fence: within radius_m of the station."""
    return distance_m(center, pos) <= radius_m


def point_inside_circle(pos: LatLon, center: LatLon, radius_m: float, margin_m: float = 5.0) -> LatLon:
    """Nearest point that is margin_m inside the circle: on the straight line from
    pos to the center. If pos is already that far inside, it's returned as is."""
    x, y = to_xy(pos, center)
    d = math.hypot(x, y)
    r = max(0.0, radius_m - margin_m)
    if d <= r:
        return pos
    return to_latlon((x * r / d, y * r / d), center)
