"""A boat that moves. Deliberately a bit mean, like the real lake:
  - the props push, water drag holds back (more drag the faster you go), so the
    boat takes a few seconds to get up to speed and coasts when you let go
  - turning lags behind the command (the hull has to start and stop rotating)
  - the right thruster is 4 % weaker than the left, as real ones never match
  - the current pushes the boat, and it slowly changes strength and direction
  - GPS error wanders slowly; the compass is a few degrees off, plus noise

  - floating trash drifts on the current; the boat only collects a piece that
    passes between its pontoons while the conveyor runs (see "Trash" below)

Everything random comes from seeded generators, so a run is repeatable.

Local frame: x east, y north, meters from the station. Heading in degrees,
0 = north, clockwise. lat/lon come from the frame with a flat-earth conversion
around ORIGIN, which is also where the station stands.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

M_PER_DEG_LAT = 111_320.0

TRASH_KINDS = ("bottle", "bag", "cup", "can")


@dataclass
class TrashPiece:
    """One floating piece of litter. x/y are its TRUE position (m east/north of
    the station); the real boat never knows these, only the sim does."""

    id: int
    x: float
    y: float
    kind: str                            # one of TRASH_KINDS
    collected: bool = False
    collected_t: float | None = None     # sim seconds when it went up the belt


@dataclass
class World:
    origin: tuple[float, float] = (39.0912, -77.1534)   # station, lat/lon
    current_mps: tuple[float, float] = (0.05, 0.02)      # east, north; the average push on the boat (a calm day)
    gps_noise_m: float = 1.5                             # std dev per axis
    radio_range_m: float = 200.0                         # signal hits -88 dBm here
    start_xy: tuple[float, float] = (4.5, 9.5)           # where the boat launches: alongside the jetty tip
    trash_count: int = 30                                # floating pieces at the start (0 = a clean lake)
    seed: int = 7


@dataclass
class BoatPhysics:
    world: World
    x: float = 0.0
    y: float = 0.0
    heading_deg: float = 0.0
    speed_mps: float = 0.0          # through the water, along the heading (the current comes on top)
    yaw_rate_dps: float = 0.0
    left: float = 0.0
    right: float = 0.0
    conveyor: bool = False
    batt_v: float = 12.6
    moored: bool = True             # tied up at the jetty until the first motor command (a real boat
                                    # doesn't drift off while the crew is still setting up)
    t: float = 0.0                  # sim seconds since start
    rng: random.Random | None = None   # GPS/compass/signal noise; seeded from world.seed
    trash: list[TrashPiece] = field(default_factory=list)   # SIM ONLY: true positions of the litter

    MAX_SPEED = 1.5        # m/s at full throttle, both motors
    MAX_YAW = 60.0         # deg/s at full differential
    YAW_LAG = 0.4          # seconds for the turn rate to catch up with the command
    # Surge: accel = THRUST * (push of both props) - DRAG_Q * v|v| - DRAG_L * v
    # A prop's push grows with the square of its speed, and so does water drag,
    # so top speed ends up roughly proportional to throttle (0.6 -> ~0.86 m/s),
    # while getting up to speed and coasting take a few seconds, like a real hull.
    DRAG_Q = 0.5           # 1/m
    DRAG_L = 0.1           # 1/s, a little linear drag so the boat really comes to rest
    THRUST = DRAG_Q * MAX_SPEED**2 + DRAG_L * MAX_SPEED   # m/s^2 at full throttle: top speed = MAX_SPEED
    LEFT_GAIN = 1.0
    RIGHT_GAIN = 0.96      # the right thruster is 4 % weaker; left = right drifts slightly right
    COMPASS_BIAS_DEG = 3.0 # a compass is never perfectly calibrated
    COMPASS_NOISE_DEG = 2.0
    DRAIN_V_PER_S_IDLE = 0.00002
    DRAIN_V_PER_S_FULL = 0.0008     # ~45 min from 12.6 to 10.5 at full throttle

    # Trash. The Rev C boat is a catamaran: the water between the two pontoons is
    # funnelled onto the conveyor belt at the bow, so a piece is only collected
    # when it is inside that gap, just ahead of the boat's center, while the
    # belt runs and the boat is actually moving forward (a stopped belt or a
    # stopped boat just pushes the litter around).
    FUNNEL_HALF_WIDTH_M = 0.4   # the gap between the pontoons is ~0.8 m
    FUNNEL_NEAR_M = 0.2         # ahead of the boat's center ...
    FUNNEL_FAR_M = 0.9          # ... up to the bow
    COLLECT_MIN_SPEED_MPS = 0.1
    TRASH_DRIFT_FACTOR = 0.9    # a floating object follows ~90 % of the current (wind and drag take the rest)
    TRASH_WALK_M = 0.03         # random wander per piece per second (std dev), m: waves and eddies
    TRASH_EVERY_S = 0.1         # drift bookkeeping at 10 Hz, not every step, to keep the fast-time runs fast
    TRASH_WALK_EVERY_S = 1.0    # the random wander only needs to be drawn once a second
    TRASH_Y_MIN_M = 12.0        # spawn zone: this far north of the station ...
    TRASH_Y_MAX_M = 70.0
    TRASH_X_MAX_M = 45.0        # ... and this far east/west
    TRASH_SPACING_M = 3.0       # never two pieces closer than this
    TRASH_LAUNCH_CLEAR_M = 4.0  # nothing right at the jetty: the first meters stay clean
    SHORE_Y_M = 2.0             # nothing floats south of this: it's the beach

    def __post_init__(self) -> None:
        self.x, self.y = self.world.start_xy
        if self.rng is None:
            self.rng = random.Random(self.world.seed)
        # The current's slow gusts: a few slow waves with random (but seeded) phases.
        # Separate generator, so changing the gusts doesn't change the GPS noise.
        g = random.Random(self.world.seed + 1000)
        self._gust_phase = [g.uniform(0, 2 * math.pi) for _ in range(4)]
        self._gps_last_t: float | None = None
        self.gps_bias_x = 0.0
        self.gps_bias_y = 0.0
        # Trash gets its own generator too, so --trash 0 leaves every other number the same.
        self._trash_rng = random.Random(self.world.seed + 2000)
        self._trash_drift_due = self.TRASH_EVERY_S
        self._trash_walk_due = self.TRASH_WALK_EVERY_S
        if not self.trash:
            self._spawn_trash(self.world.trash_count)

    # ---- trash (SIM ONLY) ----------------------------------------------------

    def _spawn_trash(self, count: int) -> None:
        """Scatter `count` pieces in the water north of the station, spaced out,
        none right where the boat launches. Seeded, so the same lake every run."""
        r = self._trash_rng
        sx, sy = self.world.start_xy
        placed: list[tuple[float, float]] = []
        for i in range(count):
            for _ in range(500):   # try a few spots; give up on a piece if the water is full
                x = r.uniform(-self.TRASH_X_MAX_M, self.TRASH_X_MAX_M)
                y = r.uniform(self.TRASH_Y_MIN_M, self.TRASH_Y_MAX_M)
                if math.hypot(x - sx, y - sy) < self.TRASH_LAUNCH_CLEAR_M:
                    continue
                if any(math.hypot(x - px, y - py) < self.TRASH_SPACING_M for px, py in placed):
                    continue
                placed.append((x, y))
                self.trash.append(TrashPiece(id=i + 1, x=x, y=y, kind=r.choice(TRASH_KINDS)))
                break

    @property
    def trash_total(self) -> int:
        return len(self.trash)

    @property
    def collected_count(self) -> int:
        return sum(1 for p in self.trash if p.collected)

    def _drift_trash(self, dt: float) -> None:
        """Floating pieces ride the current (a bit slower than the water) and
        wander a little. Collected pieces are in the basket and stay put."""
        self._trash_drift_due -= dt
        if self._trash_drift_due > 0:
            return
        step = self.TRASH_EVERY_S - self._trash_drift_due   # the time this update covers
        self._trash_drift_due = self.TRASH_EVERY_S
        cx, cy = self.current_now()
        dx = self.TRASH_DRIFT_FACTOR * cx * step
        dy = self.TRASH_DRIFT_FACTOR * cy * step
        self._trash_walk_due -= step
        walk = self._trash_walk_due <= 0
        if walk:
            self._trash_walk_due = self.TRASH_WALK_EVERY_S
        r = self._trash_rng
        for p in self.trash:
            if p.collected:
                continue
            p.x += dx
            p.y += dy
            if walk:
                p.x += r.gauss(0.0, self.TRASH_WALK_M)
                p.y += r.gauss(0.0, self.TRASH_WALK_M)
            if p.y < self.SHORE_Y_M:
                p.y = self.SHORE_Y_M   # washed up on the beach, stays there until the current turns

    def _collect_trash(self) -> None:
        """Mark every piece that is between the pontoons, just ahead of the boat's
        center, as collected. Only called while the belt runs and the boat moves
        forward, so this costs nothing the rest of the time."""
        h = math.radians(self.heading_deg)
        sh, ch = math.sin(h), math.cos(h)
        bx, by = self.x, self.y
        reach = self.FUNNEL_FAR_M + self.FUNNEL_HALF_WIDTH_M
        for p in self.trash:
            if p.collected:
                continue
            dx = p.x - bx
            dy = p.y - by
            if abs(dx) > reach or abs(dy) > reach:
                continue   # nowhere near: skip the rotation
            # the boat's own frame: ahead along the heading, side to the right of it
            ahead_m = dx * sh + dy * ch
            side_m = dx * ch - dy * sh
            if self.FUNNEL_NEAR_M <= ahead_m <= self.FUNNEL_FAR_M and abs(side_m) <= self.FUNNEL_HALF_WIDTH_M:
                p.collected = True
                p.collected_t = self.t

    def in_funnel(self, x: float, y: float) -> bool:
        """Would a piece at true (x, y) be inside the intake right now? Same rule
        as collection, minus the belt and speed conditions; handy for tests."""
        h = math.radians(self.heading_deg)
        dx, dy = x - self.x, y - self.y
        ahead_m = dx * math.sin(h) + dy * math.cos(h)
        side_m = dx * math.cos(h) - dy * math.sin(h)
        return self.FUNNEL_NEAR_M <= ahead_m <= self.FUNNEL_FAR_M and abs(side_m) <= self.FUNNEL_HALF_WIDTH_M

    def set_motors(self, left: float, right: float, conveyor: bool) -> None:
        self.left = max(-1.0, min(1.0, left))
        self.right = max(-1.0, min(1.0, right))
        self.conveyor = conveyor
        if self.left or self.right:
            self.moored = False     # cast off

    def current_now(self) -> tuple[float, float]:
        """The current at this moment, east/north m/s. Its strength swings between
        about 55 % and 145 % of the average, and its direction by about +-25
        degrees, over tens of seconds."""
        p = self._gust_phase
        strength = 1.0 + 0.3 * math.sin(2 * math.pi * self.t / 47.0 + p[0]) + 0.15 * math.sin(2 * math.pi * self.t / 19.0 + p[1])
        turn = math.radians(18.0 * math.sin(2 * math.pi * self.t / 71.0 + p[2]) + 7.0 * math.sin(2 * math.pi * self.t / 23.0 + p[3]))
        cx, cy = self.world.current_mps
        c, s = math.cos(turn), math.sin(turn)
        return strength * (cx * c - cy * s), strength * (cx * s + cy * c)

    def step(self, dt: float) -> None:
        self.t += dt
        if self.trash:
            self._drift_trash(dt)   # the lake keeps moving even while the boat is tied up
        if self.moored:
            # held by the lines: no drift, no motion; the electronics still draw a little
            self.batt_v = max(9.5, self.batt_v - self.DRAIN_V_PER_S_IDLE * dt)
            return
        l = self.left * self.LEFT_GAIN
        r = self.right * self.RIGHT_GAIN
        # surge: the props push (square law, sign kept for reverse), drag holds back
        push = (l * abs(l) + r * abs(r)) / 2.0
        v = self.speed_mps
        accel = self.THRUST * push - self.DRAG_Q * v * abs(v) - self.DRAG_L * v
        self.speed_mps += accel * dt
        # turning: rate follows the difference between the motors, with a lag
        target_yaw = (l - r) * self.MAX_YAW
        self.yaw_rate_dps += (target_yaw - self.yaw_rate_dps) * min(1.0, dt / self.YAW_LAG)
        self.heading_deg = (self.heading_deg + self.yaw_rate_dps * dt) % 360.0
        h = math.radians(self.heading_deg)
        cx, cy = self.current_now()
        self.x += (self.speed_mps * math.sin(h) + cx) * dt
        self.y += (self.speed_mps * math.cos(h) + cy) * dt
        # Judged on TRUE positions: the lake knows where the litter is, the boat doesn't.
        if self.conveyor and self.speed_mps > self.COLLECT_MIN_SPEED_MPS and self.trash:
            self._collect_trash()
        load = (abs(self.left) + abs(self.right)) / 2.0 + (0.3 if self.conveyor else 0.0)
        self.batt_v -= (self.DRAIN_V_PER_S_IDLE + self.DRAIN_V_PER_S_FULL * load) * dt
        self.batt_v = max(9.5, self.batt_v)

    # ---- what the sensors would report -------------------------------------

    def gps(self) -> tuple[float, float]:
        """One GPS fix, now. Real GPS error wanders slowly (a random walk, held
        within +-noise) plus a little jitter on each fix. The walk's step grows
        with the square root of the time since the last fix, which is how a
        random walk works: reading the GPS 5 times a second gives the same slow
        wander per second as reading it once a second."""
        n = self.world.gps_noise_m
        dt = 1.0 if self._gps_last_t is None else max(0.0, self.t - self._gps_last_t)
        self._gps_last_t = self.t
        step = n * 0.15 * math.sqrt(dt)
        self.gps_bias_x = max(-n, min(n, self.gps_bias_x + self.rng.gauss(0, step)))
        self.gps_bias_y = max(-n, min(n, self.gps_bias_y + self.rng.gauss(0, step)))
        nx = self.x + self.gps_bias_x + self.rng.gauss(0, n * 0.2)
        ny = self.y + self.gps_bias_y + self.rng.gauss(0, n * 0.2)
        return self.world_to_latlon(nx, ny)

    def compass_deg(self) -> float:
        return (self.heading_deg + self.COMPASS_BIAS_DEG + self.rng.gauss(0, self.COMPASS_NOISE_DEG)) % 360.0

    def distance_to_station_m(self) -> float:
        return math.hypot(self.x, self.y)

    def signal_dbm(self) -> float:
        d = self.distance_to_station_m()
        return -40.0 - 48.0 * (d / self.world.radio_range_m) + self.rng.gauss(0, 1.5)

    def water(self) -> tuple[float, float, float, float]:
        # a gentle gradient across the pond so the heat map has something to show
        temp = 20.0 + 0.01 * self.y
        ph = 7.0 + 0.004 * self.x
        turb = 10.0 + 0.05 * max(0.0, self.y)
        cond = 400.0 + 0.5 * self.x
        return temp, ph, turb, cond

    def world_to_latlon(self, x: float, y: float) -> tuple[float, float]:
        lat0, lon0 = self.world.origin
        lat = lat0 + y / M_PER_DEG_LAT
        lon = lon0 + x / (M_PER_DEG_LAT * math.cos(math.radians(lat0)))
        return lat, lon
