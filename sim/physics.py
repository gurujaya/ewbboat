"""A boat that moves. Deliberately a bit mean: current pushes it, GPS is noisy,
the motors don't respond instantly.

Local frame: x east, y north, meters from the station. Heading in degrees,
0 = north, clockwise. lat/lon come from the frame with a flat-earth conversion
around ORIGIN, which is also where the station stands.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

M_PER_DEG_LAT = 111_320.0


@dataclass
class World:
    origin: tuple[float, float] = (39.0912, -77.1534)   # station, lat/lon
    current_mps: tuple[float, float] = (0.15, 0.05)      # east, north; pushes the boat
    gps_noise_m: float = 1.5                             # std dev per axis
    radio_range_m: float = 200.0                         # signal hits -88 dBm here
    start_xy: tuple[float, float] = (0.0, 15.0)          # where the boat launches


@dataclass
class BoatPhysics:
    world: World
    x: float = 0.0
    y: float = 0.0
    heading_deg: float = 0.0
    speed_mps: float = 0.0
    yaw_rate_dps: float = 0.0
    left: float = 0.0
    right: float = 0.0
    conveyor: bool = False
    batt_v: float = 12.6
    rng: random.Random = field(default_factory=lambda: random.Random(7))

    MAX_SPEED = 1.5        # m/s at full throttle
    MAX_YAW = 60.0         # deg/s at full differential
    SPEED_LAG = 0.8        # seconds to reach target speed
    YAW_LAG = 0.4
    DRAIN_V_PER_S_IDLE = 0.00002
    DRAIN_V_PER_S_FULL = 0.0008     # ~45 min from 12.6 to 10.5 at full throttle

    def __post_init__(self) -> None:
        self.x, self.y = self.world.start_xy

    def set_motors(self, left: float, right: float, conveyor: bool) -> None:
        self.left = max(-1.0, min(1.0, left))
        self.right = max(-1.0, min(1.0, right))
        self.conveyor = conveyor

    def step(self, dt: float) -> None:
        target_speed = (self.left + self.right) / 2.0 * self.MAX_SPEED
        target_yaw = (self.left - self.right) * self.MAX_YAW
        self.speed_mps += (target_speed - self.speed_mps) * min(1.0, dt / self.SPEED_LAG)
        self.yaw_rate_dps += (target_yaw - self.yaw_rate_dps) * min(1.0, dt / self.YAW_LAG)
        self.heading_deg = (self.heading_deg + self.yaw_rate_dps * dt) % 360.0
        h = math.radians(self.heading_deg)
        cx, cy = self.world.current_mps
        self.x += (self.speed_mps * math.sin(h) + cx) * dt
        self.y += (self.speed_mps * math.cos(h) + cy) * dt
        load = (abs(self.left) + abs(self.right)) / 2.0 + (0.3 if self.conveyor else 0.0)
        self.batt_v -= (self.DRAIN_V_PER_S_IDLE + self.DRAIN_V_PER_S_FULL * load) * dt
        self.batt_v = max(9.5, self.batt_v)

    # ---- what the sensors would report -------------------------------------
    gps_bias_x: float = 0.0
    gps_bias_y: float = 0.0

    def gps(self) -> tuple[float, float]:
        # real GPS error wanders slowly; it doesn't jump around every reading
        n = self.world.gps_noise_m
        self.gps_bias_x = max(-n, min(n, self.gps_bias_x + self.rng.gauss(0, n * 0.15)))
        self.gps_bias_y = max(-n, min(n, self.gps_bias_y + self.rng.gauss(0, n * 0.15)))
        nx = self.x + self.gps_bias_x + self.rng.gauss(0, n * 0.2)
        ny = self.y + self.gps_bias_y + self.rng.gauss(0, n * 0.2)
        return self.world_to_latlon(nx, ny)

    def compass_deg(self) -> float:
        return (self.heading_deg + self.rng.gauss(0, 2.0)) % 360.0

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
