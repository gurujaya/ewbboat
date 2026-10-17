"""The boat's brain. One loop at 10 Hz.

    read Arduino state -> filter the GPS -> run safety checks -> pick motor command by mode -> send M line
    5 times a second: send telemetry, maybe drop a trail point, log to CSV

Position: every GPS fix goes through nav.PositionFilter; everything else on the
boat (autopilot, fences, trail, tlm) uses the filtered position. The raw fix is
only written to the CSV log, next to the filtered one, so we can compare.

Modes and every transition live in modes.py. Hardware lives in arduino.py and
comms/boatlink. This file just wires them together.
"""

from __future__ import annotations

import logging
import signal
import sys
import threading
import time

import config
from autopilot import PathFollower
from modes import AUTO, COMING_HOME, DRIVEN, Modes
from nav import PositionFilter, clamp_to_rect, mix, point_inside_circle, smooth_heading
from safety import BatteryMonitor, HomePlan, driven_fence_ok, fence_ok
from trail import Trail

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("boat")


class Boat:
    def __init__(self, ard=None, link=None, csv=None) -> None:
        """The three things that touch the outside world can be handed in: the serial link to
        the Arduino, the radio link, and the log. On the boat they're left out and the real
        ones are made here. The browser demo (sim/browser) hands in fakes and runs this same
        class, so what you see on a static web page is this file's logic."""
        if ard is None:
            from arduino import Arduino            # imported here: needs pyserial, which a browser hasn't got
            ard = Arduino(config.SERIAL_PORT, config.SERIAL_BAUD)
        if link is None:
            from radio import make_link
            link = make_link(self.signal_dbm)
        if csv is None:
            from logger import CsvLogger
            csv = CsvLogger(config.LOG_DIR)
        self.ard = ard
        self.link = link
        self.modes = Modes()
        self.trail = Trail(config.TRAIL_EVERY_M, config.TRAIL_EVERY_S, config.HOME_SETTLE_S)
        self.batt = BatteryMonitor(config.BATT_AVG_S)
        self.home = HomePlan()
        self.csv = csv
        self.lock = threading.Lock()

        self.last_cmd: dict | None = None
        self.last_cmd_at = 0.0
        self.sweep: PathFollower | None = None
        self.pending_wps: list[tuple[float, float]] | None = None
        self.fence: list[tuple[float, float]] | None = None
        self.left = self.right = 0.0
        self.conveyor = False
        self._running = True
        self._last_mode_ask: tuple[str, float] = ("", 0.0)
        self._held_events: list[dict] = []
        self.heading: float | None = None     # compass heading, smoothed (HEADING_SMOOTH_S)
        self._heading_t: float = 0.0
        self.filter = PositionFilter(config.FILTER_ALPHA, config.FILTER_BETA, config.FILTER_GAP_RESET_S, config.FILTER_JUMP_M)
        self._fence_target: tuple[float, float] | None = None   # where to go after crossing a fence

        self.link.on("cmd", self.on_cmd)
        self.link.on("wps", self.on_wps)
        self.link.on_link_lost(self.on_link_lost)
        self.link.on_link_back(self.on_link_back)

    # ---- helpers ------------------------------------------------------------
    def signal_dbm(self) -> float | None:
        if config.ENV == "sim":
            return self.ard.state.signal_dbm
        from radio import read_wifi_dbm
        return read_wifi_dbm()

    def pos(self, now: float | None = None) -> tuple[float, float]:
        """Filtered position (predicted to `now`). Falls back to the last raw fix
        before the filter has one (startup, or just after the fix came back)."""
        p = self.filter.position(time.time() if now is None else now)
        return p if p is not None else (self.ard.state.lat, self.ard.state.lon)

    def event(self, kind: str, detail: str = "") -> None:
        log.info("event %s %s", kind, detail)
        body = {"kind": kind, "detail": detail, "ts": time.time()}
        if self.link.up:
            self.link.send("evt", body)
        else:
            self._held_events.append(body)   # deliver when the link comes back

    def flush_events(self) -> None:
        held, self._held_events = self._held_events, []
        for body in held:
            self.link.send("evt", body)

    def ack(self, for_: str, ok: bool, msg: str = "") -> None:
        self.link.send("ack", {"for": for_, "ok": ok, "msg": msg})

    # ---- radio callbacks (run on the link thread) ---------------------------
    def on_cmd(self, m: dict) -> None:
        with self.lock:
            self.last_cmd = m
            self.last_cmd_at = time.time()
            want = m["mode"]
            now = time.time()
            # cmd.mode is only a request when ask is set (a button was pressed); otherwise it's informational.
            # the station repeats it for a few seconds, so only ask once every 2 s.
            if m.get("ask") and want != self.modes.mode and (want != self._last_mode_ask[0] or now - self._last_mode_ask[1] > 2.0):
                self._last_mode_ask = (want, now)
                reason = {"DRIVEN": "take_control", "AUTO": "start_sweep", "COMING_HOME": "come_home"}[want]
                self._request(want, reason)

    def on_wps(self, m: dict) -> None:
        with self.lock:
            pts = [(float(p[0]), float(p[1])) for p in m["points"]]
            self.pending_wps = pts
            lats = [p[0] for p in pts]; lons = [p[1] for p in pts]
            # the sweep rectangle, padded by the arrive radius so row ends don't count as "outside"
            pad_lat = (config.ARRIVE_M + 1.0) / 111_320.0
            pad_lon = pad_lat / max(0.2, __import__("math").cos(__import__("math").radians(lats[0])))
            self.fence = [(min(lats) - pad_lat, min(lons) - pad_lon), (max(lats) + pad_lat, max(lons) + pad_lon)]
            self.ack(m["id"], True, f"{len(pts)} points")

    def on_link_lost(self) -> None:
        with self.lock:
            self.event("link_lost", f"no station heartbeat for {self.link.seconds_since_heard():.1f} s")
            self._request(COMING_HOME, "link_lost")
            self.home.start_link_lost(time.time())

    def on_link_back(self) -> None:
        with self.lock:
            self.flush_events()
            self.event("link_back")
            if self.modes.mode == COMING_HOME and self.home.reason == "link_lost" and self.home.phase in ("WAIT", "BACKUP"):
                ch = self.modes.resume_previous()
                if ch.ok:
                    self.home.phase = "IDLE"
                    self.event("mode_change", f"resumed {ch.mode}")

    # ---- mode changes ----------------------------------------------------------
    def _request(self, want: str, reason: str) -> None:
        before = self.modes.mode
        ch = self.modes.request(
            want, reason,
            link_up=self.link.up, batt_pct=self.batt.pct,
            have_waypoints=self.pending_wps is not None, gps_fix=self.ard.state.gps_fix,
        )
        if reason in ("take_control", "start_sweep", "come_home"):
            self.ack("mode", ch.ok, ch.msg)
        if not ch.ok:
            return
        if ch.mode != before:
            self.event("mode_change", f"{before} -> {ch.mode} ({reason})")
        if ch.mode == AUTO:
            # start the path where the boat is, so the first leg is a straight run to the first waypoint
            self.sweep = PathFollower(self.pending_wps or [], start=self.pos(), label="sweep")
        elif ch.mode == COMING_HOME and reason in ("come_home", "batt_low"):
            self.home.start_home(self.trail, reason, self.pos())     # straight home, the fastest way
        elif ch.mode == COMING_HOME and reason == "fence_exit" and self._fence_target is not None:
            self.home.start_fence(self.pos(), self._fence_target)

    def _fence_exit(self, pos: tuple[float, float], inside: tuple[float, float], which: str) -> None:
        """Crossed a fence: stop what we're doing and drive to `inside`."""
        self.event("fence_exit", f"{which} fence at {pos[0]:.5f},{pos[1]:.5f}")
        self._fence_target = inside
        self._request(COMING_HOME, "fence_exit")

    # ---- the loop ------------------------------------------------------------
    def run(self) -> None:
        self.ard.start()
        self.link.start()
        period = 1.0 / config.LOOP_HZ
        next_tlm = 0.0
        log.info("boat up: env=%s serial=%s station=%s", config.ENV, config.SERIAL_PORT, config.STATION_ADDR)
        while self._running:
            t0 = time.time()
            with self.lock:
                self.tick(t0)
                # half a loop of slack: tlm every 2nd loop is 5 Hz; without it, a loop that
                # wakes a millisecond early would push tlm to every 3rd loop (3.3 Hz)
                if t0 >= next_tlm - period / 2:
                    self.telemetry(t0)
                    next_tlm = t0 + 1.0 / config.TELEMETRY_HZ
            time.sleep(max(0.0, period - (time.time() - t0)))

    def tick(self, now: float) -> None:
        st = self.ard.state
        for t, lat, lon in self.ard.take_fixes():
            self.filter.update(t, (lat, lon))
        if not st.gps_fix and self.filter.ready:
            self.filter.reset()             # no fix: don't keep coasting on an old velocity
        pos = self.pos(now)
        self.heading = smooth_heading(self.heading, st.heading_deg, now - self._heading_t, config.HEADING_SMOOTH_S)
        self._heading_t = now
        self.batt.update(st.batt_v, now)

        # --- safety checks, every tick, every mode ---
        if self.batt.crossed(config.BATT_WARN_PCT):
            self.event("batt_warn", f"{self.batt.pct:.0f} %")
        if self.batt.crossed(config.BATT_HOME_PCT):
            self.event("batt_low", f"{self.batt.pct:.0f} %, conveyor off, coming home")
            self.conveyor = False
            self._request(COMING_HOME, "batt_low")
        if self.batt.crossed(config.BATT_CUT_PCT):
            self.event("batt_critical", f"{self.batt.pct:.0f} %, motors off")
        if self.batt.pct <= config.BATT_CUT_PCT:
            self.left = self.right = 0.0
            self.ard.send_motors(0.0, 0.0, False)
            return
        # Fences (ARCHITECTURE.md, Fence): cross it -> stop -> drive to the nearest point inside.
        # AUTO: the sweep rectangle, only once the boat is inside it (first waypoint passed).
        # DRIVEN: a circle of DRIVEN_FENCE_M around the station.
        if st.gps_fix and self.filter.ready:
            sweep_fence_active = self.modes.mode == AUTO and self.sweep is not None and self.sweep.next_index >= 1
            if sweep_fence_active and not fence_ok(pos, self.fence):
                self._fence_exit(pos, clamp_to_rect(pos, self.fence), "sweep")
            elif self.modes.mode == DRIVEN and not driven_fence_ok(pos):
                inside = point_inside_circle(pos, config.ORIGIN, config.DRIVEN_FENCE_M, config.FENCE_RETURN_INSIDE_M)
                self._fence_exit(pos, inside, "driving")
        for e in st.events:
            self.event("arduino_" + e.lower())
        st.events.clear()

        # --- pick motors by mode ---
        mode = self.modes.mode
        if mode == DRIVEN:
            if self.last_cmd and now - self.last_cmd_at < config.CMD_STALE_S:
                self.left, self.right = mix(self.last_cmd["throttle"], self.last_cmd["steer"])
                self.conveyor = bool(self.last_cmd["conveyor"])
            else:
                self.left = self.right = 0.0
        elif mode == AUTO:
            # A sweep is for collecting: the belt runs the whole time, whatever the operator
            # last pressed. (The 20 % battery rule turns it off and leaves AUTO anyway.)
            self.conveyor = True
            if self.sweep and not self.sweep.done:
                self.left, self.right, passed = self.sweep.step(pos, self.heading, now)
                # one event per waypoint passed (pure pursuit can pass two in one step at a tight corner)
                n = self.sweep.next_index
                for k in range(n - passed + 1, n + 1):
                    self.event("wp_reached", f"{k}/{len(self.sweep.points)}")
            else:
                self.event("sweep_done")
                self.pending_wps = None
                self._request(COMING_HOME, "come_home")
        elif mode == COMING_HOME:
            self.conveyor = False           # nothing to collect on the way home; save the battery
            self.left, self.right, ev = self.home.step(pos, self.heading, self.trail, self.link.up, now)
            if ev:
                self.event(ev)
                if ev == "fence_back_inside":
                    # resume the sweep only if it was the sweep that crossed the fence
                    if self.modes.previous == AUTO and self.sweep and not self.sweep.done and self.pending_wps and self.link.up:
                        ch = self.modes.request(DRIVEN, "take_control", link_up=True, batt_pct=self.batt.pct)
                        ch = self.modes.request(AUTO, "start_sweep", link_up=True, batt_pct=self.batt.pct, have_waypoints=True, gps_fix=st.gps_fix)
                        self.event("mode_change", f"back inside, resuming sweep at wp {self.sweep.next_index}")
                    elif self.link.up:
                        self._request(DRIVEN, "take_control")

        self.ard.send_motors(self.left, self.right, self.conveyor)

    def telemetry(self, now: float) -> None:
        st = self.ard.state
        pos = self.pos(now)
        sig = self.signal_dbm()
        speed = self.filter.speed_mps()
        if st.gps_fix and self.filter.ready:
            p = self.trail.maybe_add(pos, sig, now)
            if p:
                self.link.send("trail", {"i": p.i, "lat": round(p.lat, 7), "lon": round(p.lon, 7), "signal_dbm": p.signal_dbm})
        mode = self.modes.mode
        target = None
        if mode == AUTO and self.sweep:
            target = self.sweep.target
        elif mode == COMING_HOME:
            target = self.home.target
        tlm = {
            "lat": round(pos[0], 7), "lon": round(pos[1], 7), "heading_deg": None if self.heading is None else round(self.heading, 1),
            "speed_mps": None if speed is None else round(speed, 2),
            "gps_fix": st.gps_fix, "sats": st.sats,
            "batt_v": None if st.batt_v != st.batt_v else round(st.batt_v, 2), "batt_pct": round(self.batt.pct),
            "signal_dbm": sig, "mode": self.modes.mode, "left": round(self.left, 2), "right": round(self.right, 2),
            "conveyor": self.conveyor, "water": st.water, "trail_len": len(self.trail.points),
            "wp_index": (self.sweep.next_index if mode == AUTO and self.sweep else None),
            "home_phase": self.home.phase if mode == COMING_HOME else None,
            "home": None if self.trail.home is None else [round(self.trail.home[0], 7), round(self.trail.home[1], 7)],
            "target": None if target is None else [round(target[0], 7), round(target[1], 7)],
        }
        self.link.send("tlm", tlm)
        # the SD card also gets the raw GPS fix (not sent over the radio)
        self.csv.write({
            "ts": now, **tlm, "raw_lat": st.lat, "raw_lon": st.lon,
            "target_lat": target[0] if target else None, "target_lon": target[1] if target else None,
        })

    def stop(self) -> None:
        self._running = False
        self.ard.stop()
        self.link.stop()
        self.csv.close()


if __name__ == "__main__":
    boat = Boat()
    signal.signal(signal.SIGTERM, lambda *_: boat.stop())
    try:
        boat.run()
    except KeyboardInterrupt:
        pass
    finally:
        boat.stop()
        sys.exit(0)
