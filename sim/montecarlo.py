"""Run the boat's brain against the lake physics hundreds of times, fast, and grade it.

    python sim/montecarlo.py                 # the full grid: ~60 runs, about 20 s
    python sim/montecarlo.py --quick         # a handful of runs, a few seconds
    python sim/montecarlo.py --runs 10       # 10 seeds per cell (more runs, tighter stats)
    python sim/montecarlo.py --csv out.csv   # one row per run, for a spreadsheet
    python sim/montecarlo.py --set KP=0.01 --set LOOKAHEAD_M=4   # try other boat-pi/config.py numbers
    python sim/montecarlo.py --phys COMPASS_NOISE_DEG=0          # or a different boat (physics.py)

No pty, no radio, no clock: the same boat-pi code the real boat runs (the GPS
filter, the path follower, the trail, the coming-home plan) is stepped through
physics.py as fast as Python can go, ten minutes of lake in under a second.
Because the physics knows the boat's TRUE position, this can measure what the
real lake can't tell us: how far the boat really was from its planned row, not
just what its noisy GPS said.

Two scenarios, each run across a grid of currents, GPS noise levels and random seeds:

  sweep   drive out from the jetty, sweep a 30 x 20 m rectangle, come straight home
  lost    drive straight out past radio range; the link drops; the boat must stop, wait,
          back up along its trail to good signal, and get the link back on its own

Each run is graded against the limits in LIMITS (explained there). Exit code 0
only if every run passes, so this can gate a pull request like headless_test.py,
in a fraction of the time. It does not replace headless_test.py: that one runs the
real processes, the real serial line and the real radio code; this one only runs
the math.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import statistics
import sys
import time
from dataclasses import dataclass, asdict
from multiprocessing import get_context

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "boat-pi"))

import config  # noqa: E402  (boat-pi's; ground-station has a config.py too, so that folder is NOT on the path)
from autopilot import PathFollower  # noqa: E402
from nav import PositionFilter, mix, smooth_heading, to_xy  # noqa: E402
from physics import BoatPhysics, World  # noqa: E402
from safety import HomePlan  # noqa: E402
from trail import Trail  # noqa: E402

# the station's sweep planner, loaded by file so its config.py doesn't shadow the boat's
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("gs_sweep", os.path.join(ROOT, "ground-station", "sweep.py"))
_sweep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sweep)
plan_sweep = _sweep.plan

# ---- pass / fail limits, with the reasoning ----------------------------------------------
LIMITS = {
    # Cross-track error while sweeping = how far from the planned row, ignoring the first 5 m
    # after each turn. Two versions:
    #   xt_ctl_*  against the position the boat could know at best (truth + the GPS's slow
    #             drift). This is the controller's own error and has a fixed limit.
    #   xt_*      against the true position. The GPS drift (up to the noise setting, per axis)
    #             adds to it and no controller can remove that, so its limit grows with the
    #             noise: see limit_for(). Rows are 3 m apart in these runs.
    "xt_ctl_rms_m": "noise",
    "xt_ctl_max_m": "noise",
    "xt_rms_m": "noise",
    "xt_max_m": "noise",
    # Never leave the sweep fence (the rectangle padded by ARRIVE_M + 1 m, as boat-pi sets it).
    "fence_min_margin_m": 0.0,
    # The trip home: the trail is at most ~100 m, at 0.6 throttle (~0.9 m/s) that's 2 minutes.
    "home_s": 300.0,
    # Where it stops vs where it launched. What the math allows: the arrival rule (within
    # ARRIVE_M = 2 m, or passing the point within 1.5 x that = 3 m), the GPS drift at that moment
    # (up to the noise setting on each axis, 1.4 x on the diagonal), and a little coasting.
    # In good GPS (1 m) that's about 4.7 m worst case; typically 2-3 m. Only a better GPS
    # (RTK) brings it down; no controller can. See limit_for().
    "home_err_m": "noise",
    # The averaged home point vs the true launch spot.
    "home_fix_err_m": 2.0,
    # How much the nose wags on a straight row (true yaw rate, RMS, deg/s). With perfect sensors
    # this hull settles to ~6; GPS jitter through the steering adds the rest. 11+ looks like
    # fishtailing on the dashboard and wastes battery.
    "sway_dps": "noise",
    # Lost link: from the moment the link drops, the boat has the link back within this.
    # It waits 10 s, then backs up ~10-20 m at ~0.9 m/s.
    "link_back_s": 120.0,
}

def limit_for(key: str, noise_m: float) -> float:
    """Limits that depend on how bad the GPS is."""
    # The GPS drift in physics.py is a random walk held within +-noise per axis; it sits near
    # the edges a lot, so its RMS on one axis is about 0.75 x noise and its worst case is noise.
    if key == "xt_rms_m":
        return math.hypot(0.8, 0.75 * noise_m)       # controller error and drift add in quadrature
    if key == "xt_max_m":
        return 1.8 + noise_m
    if key == "xt_ctl_rms_m":
        return 0.6 + 0.15 * noise_m                  # the fast jitter still gets through the filter a little
    if key == "xt_ctl_max_m":
        return 1.6 + 0.42 * noise_m
    if key == "home_err_m":
        return 3.3 + 1.45 * noise_m
    if key == "sway_dps":
        return 9.0 + 2.2 * noise_m                   # the jitter that reaches the steering grows with the noise
    return LIMITS[key]


# the grid: currents (east, north m/s) from calm to strong, GPS noise from good to poor
CURRENTS = [(0.05, 0.02), (0.15, 0.05), (0.30, 0.10), (0.00, 0.30), (-0.20, -0.10)]
NOISES = [1.0, 1.5, 3.0]
QUICK_CURRENTS = [(0.15, 0.05), (0.30, 0.10)]
QUICK_NOISES = [1.5]

DT = 0.05                 # physics step, s (the real fake_arduino ticks the firmware at 20 Hz)
GPS_EVERY_S = 0.2         # 5 Hz GPS and T lines
TICK_EVERY_S = 1.0 / config.LOOP_HZ
TLM_EVERY_S = 1.0 / config.TELEMETRY_HZ
LINK_DROP_DBM = config.SIGNAL_DROP_DBM
LINK_BACK_DBM = config.SIGNAL_DROP_DBM + 4     # boatlink needs 4 dB of margin before it trusts the link again
LINK_LOST_S = 3.0                              # no heartbeat for this long -> link lost (boatlink)


@dataclass
class Scenario:
    kind: str                       # "sweep" or "lost"
    current: tuple[float, float]
    noise_m: float
    seed: int
    radio_range_m: float = 120.0
    row_m: float = 0.65             # sweep row spacing: the station's default, 0.8 x the scoop width
    turn_rows: int = 2              # sweep.plan turn pattern (every other row first)


@dataclass
class Result:
    kind: str
    current: str
    noise_m: float
    seed: int
    ok: bool
    fails: str
    sweep_s: float | None = None
    xt_rms_m: float | None = None
    xt_max_m: float | None = None
    xt_ctl_rms_m: float | None = None
    xt_ctl_max_m: float | None = None
    xt_meas_rms_m: float | None = None     # what the boat's own (filtered) GPS thought
    sway_dps: float | None = None          # true yaw rate on the rows, RMS (deg/s): how much it wags
    scooped: int | None = None             # pieces of floating trash collected during the sweep (belt on)
    scooped_in_area: int | None = None     # of those that were inside the sweep rectangle when it started
    steer_rms: float | None = None         # left-right motor difference on the rows, RMS
    fence_min_margin_m: float | None = None
    home_s: float | None = None
    home_err_m: float | None = None
    home_fix_err_m: float | None = None
    jitter_filt_m: float | None = None     # filtered position vs truth+drift, RMS
    jitter_raw_m: float | None = None      # raw GPS vs truth+drift, RMS
    link_lost_at_s: float | None = None
    link_back_s: float | None = None
    backup_m: float | None = None          # how far it drove back before the link returned
    wall_s: float = 0.0


def rms(xs: list[float]) -> float | None:
    return math.sqrt(sum(x * x for x in xs) / len(xs)) if xs else None


def cross_track(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float, float]:
    """Distance of p from the line a->b, how far along it p is, and the line's length."""
    ax, ay = a
    bx, by = b
    length = math.hypot(bx - ax, by - ay)
    ux, uy = (bx - ax) / length, (by - ay) / length
    along = (p[0] - ax) * ux + (p[1] - ay) * uy
    cross = abs((p[0] - ax) * uy - (p[1] - ay) * ux)
    return cross, along, length


class FastBoat:
    """The pieces of boat-pi/main.py that matter for navigation, driven by a fake clock."""

    def __init__(self, sc: Scenario):
        self.world = World(current_mps=sc.current, gps_noise_m=sc.noise_m, radio_range_m=sc.radio_range_m, seed=sc.seed)
        self.conveyor = False
        self.phys = BoatPhysics(self.world)
        self.filt = PositionFilter(config.FILTER_ALPHA, config.FILTER_BETA, config.FILTER_GAP_RESET_S, config.FILTER_JUMP_M)
        self.trail = Trail(config.TRAIL_EVERY_M, config.TRAIL_EVERY_S, config.HOME_SETTLE_S)
        self.origin = self.world.origin
        self.t = 0.0
        self.next_gps = 0.0
        self.next_tick = 0.0
        self.next_tlm = 0.0
        self.fix = self.phys.gps()
        self.heading = self.phys.compass_deg()
        self.cmd = (0.0, 0.0)
        self.launch_true = (self.phys.x, self.phys.y)
        self.filt_err: list[float] = []
        self.raw_err: list[float] = []
        # link model (boatlink): packets drop below LINK_DROP_DBM; lost after LINK_LOST_S of silence;
        # back once the signal is LINK_BACK_DBM or better again
        self.link_up = True
        self.silent_since: float | None = None

    def truth(self) -> tuple[float, float]:
        return self.phys.x, self.phys.y

    def pos(self):
        return self.filt.position(self.t)

    def pos_xy(self) -> tuple[float, float] | None:
        p = self.pos()
        return None if p is None else to_xy(p, self.origin)

    def advance(self) -> bool:
        """Run physics until the next Pi tick. Returns True once the filter has a position."""
        while True:
            self.phys.set_motors(self.cmd[0], self.cmd[1], self.conveyor)
            self.phys.step(DT)
            self.t += DT
            if self.t >= self.next_gps:
                self.next_gps += GPS_EVERY_S
                self.fix = self.phys.gps()
                self.heading = smooth_heading(self.heading, self.phys.compass_deg(), GPS_EVERY_S, config.HEADING_SMOOTH_S)
                self.filt.update(self.t, self.fix)
            sig = self.phys.signal_dbm()
            if sig < LINK_DROP_DBM:
                self.silent_since = self.silent_since or self.t
                if self.link_up and self.t - self.silent_since >= LINK_LOST_S:
                    self.link_up = False
            elif sig >= LINK_BACK_DBM:
                self.silent_since = None
                self.link_up = True
            if self.t >= self.next_tick:
                self.next_tick += TICK_EVERY_S
                break
        p = self.pos()
        if p is None:
            return False
        if self.t >= self.next_tlm:
            self.next_tlm += TLM_EVERY_S
            self.trail.maybe_add(p, sig, self.t)
        # how far the filtered and raw positions are from the truth (plus the GPS's own slow
        # drift, which nothing on the boat can see)
        if self.t > 3:
            bx, by = self.phys.x + self.phys.gps_bias_x, self.phys.y + self.phys.gps_bias_y
            fx, fy = to_xy(p, self.origin)
            rx, ry = to_xy(self.fix, self.origin)
            self.filt_err.append(math.hypot(fx - bx, fy - by))
            self.raw_err.append(math.hypot(rx - bx, ry - by))
        return True


def run_sweep(sc: Scenario) -> Result:
    b = FastBoat(sc)
    r = Result(sc.kind, f"{sc.current[0]:+.2f},{sc.current[1]:+.2f}", sc.noise_m, sc.seed, ok=True, fails="")
    phase, t0 = "drive", 0.0
    follower = None
    pts_xy = []
    xt_true: list[float] = []
    xt_ctl: list[float] = []
    xt_meas: list[float] = []
    yaw_rates: list[float] = []
    steers: list[float] = []
    margins: list[float] = []
    while b.t < 2400:
        if not b.advance():
            continue
        pos = b.pos()
        pxy = to_xy(pos, b.origin)
        if phase == "drive":
            b.cmd = mix(0.8, 0.0)                    # straight out from the jetty
            if b.t > 8:
                lat, lon = pos
                dlat, dlon = 20 / 111320, 30 / (111320 * math.cos(math.radians(lat)))
                corners = [(lat + dlat * 0.3, lon - dlon / 2), (lat + dlat * 1.3, lon + dlon / 2)]
                pts = plan_sweep(corners, sc.row_m, turn_rows=sc.turn_rows)
                pts_xy = [to_xy(p, b.origin) for p in pts]
                pad = config.ARRIVE_M + 1.0
                fence = (min(q[0] for q in pts_xy) - pad, max(q[0] for q in pts_xy) + pad, min(q[1] for q in pts_xy) - pad, max(q[1] for q in pts_xy) + pad)
                follower = PathFollower(pts, start=pos, label="sweep")
                phase, t0 = "sweep", b.t
                b.conveyor = True           # AUTO runs the belt (boat-pi/main.py)
                xs = [q[0] for q in pts_xy]; ys = [q[1] for q in pts_xy]
                in_area = sum(1 for tp in b.phys.trash if not tp.collected and min(xs) <= tp.x <= max(xs) and min(ys) <= tp.y <= max(ys))
        elif phase == "sweep":
            l, rr, _ = follower.step(pos, b.heading, b.t)
            b.cmd = (l, rr)
            i = follower.next_index
            if i >= 1:
                # the fence is judged where the boat could at best know it is (truth + GPS drift):
                # a negative margin means the real boat-pi fence check would have fired
                tx, ty = b.truth()
                tx, ty = tx + b.phys.gps_bias_x, ty + b.phys.gps_bias_y
                margins.append(min(tx - fence[0], fence[1] - tx, ty - fence[2], fence[3] - ty))
            if i % 2 == 1 and i < len(pts_xy):          # on a row (odd index = heading for a row's end)
                c, along, length = cross_track(b.truth(), pts_xy[i - 1], pts_xy[i])
                if 5 <= along <= length:
                    xt_true.append(c)
                if 10 <= along <= length - 2:
                    # the wag is judged on the straight middle of the row: a tight turn into a row
                    # a boat-width away takes a few meters to settle, and that's the turn, not wag
                    yaw_rates.append(b.phys.yaw_rate_dps)
                    steers.append(l - rr)
                    tx, ty = b.truth()
                    xt_ctl.append(cross_track((tx + b.phys.gps_bias_x, ty + b.phys.gps_bias_y), pts_xy[i - 1], pts_xy[i])[0])
                cm, alm, _ = cross_track(pxy, pts_xy[i - 1], pts_xy[i])
                if 5 <= alm <= length:
                    xt_meas.append(cm)
            if follower.done:
                r.sweep_s = b.t - t0
                b.conveyor = False          # COMING_HOME turns it off
                r.scooped, r.scooped_in_area = b.phys.collected_count, in_area
                # like boat-pi after sweep_done / Come home: straight to the launch point
                follower = PathFollower([b.trail.home], start=pos, label="home")
                phase, t0 = "home", b.t
        elif phase == "home":
            l, rr, _ = follower.step(pos, b.heading, b.t)
            b.cmd = (l, rr)
            if follower.done:
                r.home_s = b.t - t0
                b.cmd = (0.0, 0.0)
                break
    r.xt_rms_m, r.xt_max_m = rms(xt_true), (max(xt_true) if xt_true else None)
    r.xt_ctl_rms_m, r.xt_ctl_max_m = rms(xt_ctl), (max(xt_ctl) if xt_ctl else None)
    r.xt_meas_rms_m = rms(xt_meas)
    r.sway_dps, r.steer_rms = rms(yaw_rates), rms(steers)
    r.fence_min_margin_m = min(margins) if margins else None
    tx, ty = b.truth()
    r.home_err_m = math.hypot(tx - b.launch_true[0], ty - b.launch_true[1])
    if b.trail.home:
        hx, hy = to_xy(b.trail.home, b.origin)
        r.home_fix_err_m = math.hypot(hx - b.launch_true[0], hy - b.launch_true[1])
    r.jitter_filt_m, r.jitter_raw_m = rms(b.filt_err), rms(b.raw_err)
    keys = ["home_s", "home_err_m", "home_fix_err_m"]
    # The sweep fence is the rectangle padded by ARRIVE_M + 1 m (3 m). GPS noise of that size can
    # put the boat's own position outside it on a row end no matter how it steers, so the fence
    # is only graded when the noise is clearly below the padding.
    if sc.noise_m < 2.5:
        keys.append("fence_min_margin_m")
    # Row-tracking and wag are only graded when the GPS can resolve the rows. With 3 m GPS noise and
    # rows 0.65 m apart the follower can't always tell which row it's on; the sweep still covers
    # (the strip is wider than the row spacing) but the numbers say nothing about the controller.
    if sc.noise_m <= 3.0 * sc.row_m:
        keys += ["xt_ctl_rms_m", "xt_ctl_max_m", "xt_rms_m", "xt_max_m", "sway_dps"]
    else:
        r.fails = "(rows not graded: GPS noise > 3x row spacing) "
    grade(r, keys)
    return r


def run_lost(sc: Scenario) -> Result:
    b = FastBoat(sc)
    r = Result(sc.kind, f"{sc.current[0]:+.2f},{sc.current[1]:+.2f}", sc.noise_m, sc.seed, ok=True, fails="")
    home = HomePlan()
    lost_at = None
    lost_xy = None
    while b.t < 900:
        if not b.advance():
            continue
        pos = b.pos()
        if lost_at is None:
            b.cmd = mix(1.0, 0.0)                    # straight out, full throttle, until the link drops
            if not b.link_up:
                lost_at = b.t
                lost_xy = b.truth()
                r.link_lost_at_s = lost_at
                home.start_link_lost(b.t)
            continue
        l, rr, _ = home.step(pos, b.heading, b.trail, b.link_up, b.t)
        b.cmd = (l, rr)
        if b.link_up and home.phase in ("WAIT", "BACKUP"):
            # main.py resumes the previous mode here; for the grade, the link is back
            r.link_back_s = b.t - lost_at
            tx, ty = b.truth()
            r.backup_m = math.hypot(tx - lost_xy[0], ty - lost_xy[1])
            break
        if home.phase == "DONE":
            break
    r.jitter_filt_m, r.jitter_raw_m = rms(b.filt_err), rms(b.raw_err)
    if lost_at is None:
        r.ok, r.fails = False, "link never dropped (radio range too big for the fence?)"
    else:
        grade(r, ["link_back_s"])
    return r


def grade(r: Result, keys: list[str]) -> None:
    fails = []
    for k in keys:
        v = getattr(r, k)
        lim = limit_for(k, r.noise_m)
        if v is None:
            fails.append(f"{k} missing")
        elif k == "fence_min_margin_m":
            if v < lim:
                fails.append(f"{k} {v:.2f} < {lim}")
        elif v > lim:
            fails.append(f"{k} {v:.2f} > {lim}")
    note = r.fails if r.fails.startswith("(") else ""
    r.ok, r.fails = not fails, note + "; ".join(fails)


def run_one(sc: Scenario) -> Result:
    t = time.perf_counter()
    r = run_sweep(sc) if sc.kind == "sweep" else run_lost(sc)
    r.wall_s = time.perf_counter() - t
    return r


def summarize(rows: list[Result], key: str) -> str:
    vals = [getattr(x, key) for x in rows if getattr(x, key) is not None]
    if not vals:
        return f"  {key:<20} (no data)"
    vals.sort()
    p95 = vals[min(len(vals) - 1, int(0.95 * len(vals)))]
    lim = LIMITS.get(key)
    lim_s = "" if lim is None else ("   limit grows with GPS noise" if lim == "noise" else f"   limit {lim}")
    return f"  {key:<20} mean {statistics.fmean(vals):7.2f}   p95 {p95:7.2f}   worst {vals[-1] if key != 'fence_min_margin_m' else vals[0]:7.2f}" + lim_s


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--runs", type=int, default=4, help="random seeds per grid cell (default 4)")
    ap.add_argument("--quick", action="store_true", help="a small grid: 2 currents, 1 noise level, 2 seeds")
    ap.add_argument("--kind", choices=["sweep", "lost", "all"], default="all")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--csv", help="write one row per run to this file")
    ap.add_argument("--seed-base", type=int, default=100)
    ap.add_argument("--rows", type=float, default=0.65, help="sweep row spacing in m (default 0.65 = the station's)")
    ap.add_argument("--turn-rows", type=int, default=2, help="sweep.plan turn pattern: 1 = U-turn into the next row, 2 = every other row first")
    ap.add_argument("--currents", help="currents to run, as e1,n1;e2,n2 m/s (default 5 from calm to strong)")
    ap.add_argument("--noises", help="GPS noise levels to run, comma-separated meters (default 1.0,1.5,3.0)")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VAL", help="override a boat-pi/config.py value (tuning)")
    ap.add_argument("--phys", action="append", default=[], metavar="KEY=VAL", help="override a BoatPhysics constant (a different boat)")
    args = ap.parse_args()
    for kv in args.set:
        k, v = kv.split("=", 1)
        setattr(config, k, float(v))
    for kv in args.phys:
        k, v = kv.split("=", 1)
        setattr(BoatPhysics, k, float(v))

    currents, noises, runs = (QUICK_CURRENTS, QUICK_NOISES, min(2, args.runs)) if args.quick else (CURRENTS, NOISES, args.runs)
    if args.noises:
        noises = [float(v) for v in args.noises.split(",")]
    if args.currents:
        currents = [tuple(float(v) for v in c.split(",")) for c in args.currents.split(";")]
    kinds = ["sweep", "lost"] if args.kind == "all" else [args.kind]
    scenarios = [Scenario(k, c, n, args.seed_base + i, row_m=args.rows, turn_rows=args.turn_rows) for k in kinds for c in currents for n in noises for i in range(runs)]
    print(f"{len(scenarios)} runs on {args.workers} workers ...", flush=True)
    t0 = time.perf_counter()
    # Fork the workers (macOS would "spawn" fresh ones by default, and they'd re-import a clean
    # config without the --set/--phys overrides above). Forking copies this process as it is.
    with get_context("fork").Pool(args.workers) as pool:
        results = pool.map(run_one, scenarios)
    wall = time.perf_counter() - t0

    for kind in kinds:
        rows = [r for r in results if r.kind == kind]
        print(f"\n== {kind}: {sum(r.ok for r in rows)}/{len(rows)} passed ==")
        if kind == "sweep":
            print(f"  {'current':<12}{'noise':>6}{'seed':>6}  {'sweep s':>8}{'ctl rms':>8}{'ctl max':>8}{'xt rms':>8}{'xt max':>8}{'fence':>7}{'home s':>8}{'home err':>9}{'home fix':>9}  result")
            for r in rows:
                f = lambda v, d=2: "   -" if v is None else f"{v:.{d}f}"
                print(f"  {r.current:<12}{r.noise_m:>6.1f}{r.seed:>6}  {f(r.sweep_s,0):>8}{f(r.xt_ctl_rms_m):>8}{f(r.xt_ctl_max_m):>8}{f(r.xt_rms_m):>8}{f(r.xt_max_m):>8}{f(r.fence_min_margin_m,1):>7}{f(r.home_s,0):>8}{f(r.home_err_m,1):>9}{f(r.home_fix_err_m):>9}  {'ok' if r.ok else 'FAIL ' + r.fails}")
            for k in ("scooped", "scooped_in_area", "xt_ctl_rms_m", "xt_ctl_max_m", "xt_rms_m", "xt_max_m", "xt_meas_rms_m", "sway_dps", "steer_rms", "fence_min_margin_m", "sweep_s", "home_s", "home_err_m", "home_fix_err_m", "jitter_filt_m", "jitter_raw_m"):
                print(summarize(rows, k))
        else:
            print(f"  {'current':<12}{'noise':>6}{'seed':>6}  {'lost at':>8}{'back in':>8}{'backup m':>9}  result")
            for r in rows:
                f = lambda v, d=1: "   -" if v is None else f"{v:.{d}f}"
                print(f"  {r.current:<12}{r.noise_m:>6.1f}{r.seed:>6}  {f(r.link_lost_at_s,0):>8}{f(r.link_back_s,0):>8}{f(r.backup_m):>9}  {'ok' if r.ok else 'FAIL ' + r.fails}")
            for k in ("link_back_s", "backup_m"):
                print(summarize(rows, k))

    if args.csv:
        with open(args.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(asdict(results[0]).keys()))
            w.writeheader()
            w.writerows(asdict(r) for r in results)
        print(f"\nwrote {args.csv}")

    failed = [r for r in results if not r.ok]
    sim_s = sum(r.wall_s for r in results)
    print(f"\n{len(results) - len(failed)}/{len(results)} runs passed in {wall:.1f} s wall ({sim_s:.1f} s of CPU)")
    for r in failed:
        print(f"  FAIL {r.kind} current {r.current} noise {r.noise_m} seed {r.seed}: {r.fails}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
