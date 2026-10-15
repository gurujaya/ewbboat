"""The boat's brain. One loop at 10 Hz.

    read Arduino state -> run safety checks -> pick motor command by mode -> send M line
    once a second: send telemetry, maybe drop a trail point, log to CSV

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
from arduino import Arduino
from autopilot import WaypointRunner
from logger import CsvLogger
from modes import AUTO, COMING_HOME, DRIVEN, Modes
from nav import mix
from radio import make_link, read_wifi_dbm
from safety import BatteryMonitor, HomePlan, fence_ok
from trail import Trail

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("boat")


class Boat:
    def __init__(self) -> None:
        self.ard = Arduino(config.SERIAL_PORT, config.SERIAL_BAUD)
        self.link = make_link(self.signal_dbm)
        self.modes = Modes()
        self.trail = Trail(config.TRAIL_EVERY_M, config.TRAIL_EVERY_S)
        self.batt = BatteryMonitor(config.BATT_AVG_S)
        self.home = HomePlan()
        self.csv = CsvLogger(config.LOG_DIR)
        self.lock = threading.Lock()

        self.last_cmd: dict | None = None
        self.last_cmd_at = 0.0
        self.sweep: WaypointRunner | None = None
        self.pending_wps: list[tuple[float, float]] | None = None
        self.fence: list[tuple[float, float]] | None = None
        self.left = self.right = 0.0
        self.conveyor = False
        self._running = True
        self._last_mode_ask: tuple[str, float] = ("", 0.0)
        self._held_events: list[dict] = []

        self.link.on("cmd", self.on_cmd)
        self.link.on("wps", self.on_wps)
        self.link.on_link_lost(self.on_link_lost)
        self.link.on_link_back(self.on_link_back)

    # ---- helpers ------------------------------------------------------------
    def signal_dbm(self) -> float | None:
        if config.ENV == "sim":
            return self.ard.state.signal_dbm
        return read_wifi_dbm()

    def pos(self) -> tuple[float, float]:
        return self.ard.state.lat, self.ard.state.lon

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
            self.sweep = WaypointRunner(self.pending_wps or [], "sweep")
        elif ch.mode == COMING_HOME and reason in ("come_home", "batt_low"):
            self.home.start_home(self.trail, reason)
        elif ch.mode == COMING_HOME and reason == "fence_exit":
            self.home.start_fence(self.pos(), self.fence)

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
                if t0 >= next_tlm:
                    self.telemetry(t0)
                    next_tlm = t0 + 1.0 / config.TELEMETRY_HZ
            time.sleep(max(0.0, period - (time.time() - t0)))

    def tick(self, now: float) -> None:
        st = self.ard.state
        pos = self.pos()
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
        # the fence is the sweep rectangle; it only applies once the boat is inside it (first waypoint reached)
        fence_active = self.modes.mode == AUTO and self.sweep is not None and self.sweep.i >= 1
        if st.gps_fix and fence_active and not fence_ok(pos, self.fence):
            self.event("fence_exit", f"at {pos[0]:.5f},{pos[1]:.5f}")
            self._request(COMING_HOME, "fence_exit")
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
            if self.sweep and not self.sweep.done:
                self.left, self.right, reached = self.sweep.step(pos, st.heading_deg)
                if reached:
                    self.event("wp_reached", f"{self.sweep.i}/{len(self.sweep.points)}")
            else:
                self.event("sweep_done")
                self.pending_wps = None
                self._request(COMING_HOME, "come_home")
        elif mode == COMING_HOME:
            self.left, self.right, ev = self.home.step(pos, st.heading_deg, self.trail, self.link.up, now)
            if ev:
                self.event(ev)
                if ev == "fence_back_inside":
                    if self.sweep and not self.sweep.done and self.pending_wps and self.link.up:
                        ch = self.modes.request(DRIVEN, "take_control", link_up=True, batt_pct=self.batt.pct)
                        ch = self.modes.request(AUTO, "start_sweep", link_up=True, batt_pct=self.batt.pct, have_waypoints=True, gps_fix=st.gps_fix)
                        self.event("mode_change", f"back inside, resuming sweep at wp {self.sweep.i}")
                    elif self.link.up:
                        self._request(DRIVEN, "take_control")

        self.ard.send_motors(self.left, self.right, self.conveyor)

    def telemetry(self, now: float) -> None:
        st = self.ard.state
        pos = self.pos()
        sig = self.signal_dbm()
        if st.gps_fix:
            p = self.trail.maybe_add(pos, sig, now)
            if p:
                self.link.send("trail", {"i": p.i, "lat": p.lat, "lon": p.lon, "signal_dbm": p.signal_dbm})
        tlm = {
            "lat": st.lat, "lon": st.lon, "heading_deg": st.heading_deg, "speed_mps": None,
            "gps_fix": st.gps_fix, "sats": st.sats,
            "batt_v": None if st.batt_v != st.batt_v else round(st.batt_v, 2), "batt_pct": round(self.batt.pct),
            "signal_dbm": sig, "mode": self.modes.mode, "left": round(self.left, 2), "right": round(self.right, 2),
            "conveyor": self.conveyor, "water": st.water, "trail_len": len(self.trail.points),
            "wp_index": (self.sweep.i if self.modes.mode == AUTO and self.sweep else None),
            "home_phase": self.home.phase if self.modes.mode == COMING_HOME else None,
        }
        self.link.send("tlm", tlm)
        self.csv.write({"ts": now, **tlm})

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
