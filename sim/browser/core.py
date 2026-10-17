"""The simulator with no server at all: the whole thing in one Python process, meant to run
inside a web page (Pyodide, see sim/viewer/js/worker/sim.worker.js), so the demo can live on
a static host like GitHub Pages or Vercel with nothing to keep running.

What's real here: the boat's brain is the real `Boat` class from boat-pi/main.py, and the shore
side is the real `Station` class from ground-station/main.py, each handed fakes for the parts
that touch hardware or the network:

    Boat     <-- FakeArduino (physics.py behind the same T-line fields; 5 Hz GPS; 2 s watchdog)
    Boat     <-- FakeLink "boat"    }  deliver to each other in memory, through boatlink's own
    Station  <-- FakeLink "station" }  encode/decode, with the same drop-below -88 dBm rule
    Station  --> FakeClient per browser tab (what a WebSocket would carry, queued for the page)

What's not: the Arduino firmware's C++ (boat-arduino) and the UDP code in comms/boatlink don't
run in a browser. The real simulator (sim/run.py) runs both; this one runs their rules in Python.

This file is plain Python and also runs under CPython (sim/tests/test_browser_sim.py), so the
browser demo is tested without a browser.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
os.environ.setdefault("BOAT_ENV", "sim")

import importlib.util  # noqa: E402


def _load(name: str, folder: str, file: str = "main.py"):
    """Import <folder>/<file> as module `name`, with that folder first on the path while it
    loads, so its own `import config` (both the boat and the station have a config.py and a
    main.py) finds the right one."""
    folder = os.path.join(ROOT, folder)
    saved = sys.modules.pop("config", None)
    sys.path.insert(0, folder)
    try:
        spec = importlib.util.spec_from_file_location(name, os.path.join(folder, file))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        cfg = sys.modules.get("config")
    finally:
        sys.path.remove(folder)
        if saved is not None:
            sys.modules["config"] = saved
        else:
            sys.modules.pop("config", None)
    return mod, cfg


for sub in ("comms", "sim"):
    p = os.path.join(ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)

boat_main, boat_config = _load("boat_main", "boat-pi")
station_main, station_config = _load("station_main", "ground-station")
Boat = boat_main.Boat
Station = station_main.Station

from boatlink.messages import BadMessage, decode, encode  # noqa: E402
from physics import BoatPhysics, World  # noqa: E402

WATCHDOG_S = 2.0
HEARTBEAT_S = 0.25
LINK_LOST_S = 3.0


# ---------------------------------------------------------------------------------------------
# the Arduino, as the Pi sees it: boat-pi/arduino.py's state fields, fed from the physics
# ---------------------------------------------------------------------------------------------
@dataclass
class FakeArduinoState:
    lat: float = 0.0
    lon: float = 0.0
    heading_deg: float = 0.0
    gps_fix: bool = False
    sats: int = 0
    batt_v: float = float("nan")
    water: dict = field(default_factory=lambda: {"temp_c": None, "ph": None, "turb_ntu": None, "cond_us": None})
    signal_dbm: float | None = None
    last_t_line: float = 0.0
    events: list = field(default_factory=list)
    fixes: list = field(default_factory=list)


class FakeArduino:
    """Stands in for boat-pi/arduino.py: the Pi reads `state`, calls take_fixes() and
    send_motors(). Behind it, physics.py plays the lake, and the firmware's two safety rules
    that matter to the Pi are kept: a T line 5 times a second, motors cut after 2 s of silence."""

    def __init__(self, phys: BoatPhysics):
        self.phys = phys
        self.state = FakeArduinoState()
        self._next_t = 0.0
        self._last_m = 0.0
        self._stopped = False

    def start(self) -> None: ...
    def stop(self) -> None: ...

    def take_fixes(self):
        fixes, self.state.fixes = self.state.fixes, []
        return fixes

    def send_motors(self, left: float, right: float, conveyor: bool) -> None:
        self.phys.set_motors(left, right, conveyor)
        self._last_m = time.time()
        self._stopped = False

    def update(self, now: float) -> None:
        """Called by the sim loop: the T line at 5 Hz, the watchdog every time."""
        if now - self._last_m > WATCHDOG_S and (self.phys.left or self.phys.right or self.phys.conveyor):
            self.phys.set_motors(0.0, 0.0, False)
            if not self._stopped:
                self.state.events.append("STOP_NO_PI")
                self._stopped = True
        if now >= self._next_t:
            self._next_t = now + 0.2
            st = self.state
            st.lat, st.lon = self.phys.gps()
            st.heading_deg = self.phys.compass_deg()
            st.gps_fix, st.sats = True, 9
            st.batt_v = self.phys.batt_v
            t, ph, tu, c = self.phys.water()
            st.water = {"temp_c": round(t, 1), "ph": round(ph, 2), "turb_ntu": round(tu, 1), "cond_us": round(c)}
            st.signal_dbm = round(self.phys.signal_dbm(), 1)
            st.last_t_line = now
            st.fixes.append((now, st.lat, st.lon))


# ---------------------------------------------------------------------------------------------
# the radio: comms/boatlink's Link API, delivered in memory, with the same rules
# ---------------------------------------------------------------------------------------------
class FakeLink:
    def __init__(self, name: str, drop_when=None):
        self.name = name
        self.peer: FakeLink | None = None
        self.drop_when = drop_when
        self._handlers: dict[str, list] = {}
        self._on_lost: list = []
        self._on_back: list = []
        self._last_heard = 0.0
        self._last_seq = -1
        self._up = False
        self._next_hb = 0.0

    def on(self, t, fn): self._handlers.setdefault(t, []).append(fn)
    def on_link_lost(self, fn): self._on_lost.append(fn)
    def on_link_back(self, fn): self._on_back.append(fn)
    def start(self) -> None: ...
    def stop(self) -> None: ...

    @property
    def up(self) -> bool:
        return self._up

    def seconds_since_heard(self) -> float:
        return time.time() - self._last_heard if self._last_heard else float("inf")

    def send(self, t: str, body: dict | None = None) -> None:
        if self.drop_when and self.drop_when():
            return
        data = encode(t, body)              # the real wire format, validated the real way
        if self.peer is not None:
            self.peer._deliver(data)

    def _deliver(self, data: bytes) -> None:
        if self.drop_when and self.drop_when():
            return
        try:
            msg = decode(data)
        except BadMessage:
            return
        self._heard()
        if msg["t"] == "cmd":
            if msg["seq"] <= self._last_seq:
                return
            self._last_seq = msg["seq"]
        for fn in self._handlers.get(msg["t"], []):
            fn(msg)

    def step(self, now: float) -> None:
        """Heartbeats out, lost-link check: what the Link's two threads do."""
        if now >= self._next_hb:
            self._next_hb = now + HEARTBEAT_S
            self.send("hb", {"from": self.name})
        if self._up and self.seconds_since_heard() > LINK_LOST_S:
            self._up = False
            for fn in self._on_lost:
                fn()

    def _heard(self) -> None:
        self._last_heard = time.time()
        if not self._up:
            self._up = True
            for fn in self._on_back:
                fn()


def out_of_range_rule(signal_fn):
    """boat-pi/radio.py's hysteresis: drop below SIGNAL_DROP_DBM, back only 4 dB above it."""
    state = {"dropped": False}

    def rule() -> bool:
        s = signal_fn()
        if s is None:
            return False
        if state["dropped"]:
            if s > boat_config.SIGNAL_DROP_DBM + 4:
                state["dropped"] = False
        elif s < boat_config.SIGNAL_DROP_DBM:
            state["dropped"] = True
        return state["dropped"]

    return rule


class FakeClient:
    """A browser tab, from the Station's point of view: whatever it would send down the
    WebSocket is queued here for the page to pick up."""

    def __init__(self):
        self.queue: list[str] = []

    async def send_text(self, data: str) -> None:
        self.queue.append(data)


class NullCsv:
    def write(self, row: dict) -> None: ...
    def close(self) -> None: ...


class MemDB:
    """The station's SQLite, minus the file: enough for the CSV export."""

    def __init__(self):
        self.tlm: list[dict] = []

    def save(self, m: dict) -> None:
        if m.get("t") == "tlm":
            self.tlm.append(m)

    def save_sweep(self, *a) -> None: ...

    def tlm_rows(self) -> list[dict]:
        return self.tlm


# ---------------------------------------------------------------------------------------------
# the whole lake in one object
# ---------------------------------------------------------------------------------------------
class BrowserSim:
    def __init__(self, current=(0.05, 0.02), noise_m=1.5, radio_range_m=200.0, trash=30, seed=7):
        self.world = World(current_mps=tuple(current), gps_noise_m=noise_m, radio_range_m=radio_range_m, trash_count=trash, seed=seed)
        self.phys = BoatPhysics(self.world)
        self.ard = FakeArduino(self.phys)
        boat_link = FakeLink("boat", out_of_range_rule(lambda: self.ard.state.signal_dbm))
        station_link = FakeLink("station")
        boat_link.peer, station_link.peer = station_link, boat_link
        self.boat = Boat(ard=self.ard, link=boat_link, csv=NullCsv())
        self.station = Station(link=station_link, db=MemDB())
        self.clients: dict[str, FakeClient] = {}
        self._last_step = time.time()
        self._next_tick = 0.0
        self._next_tlm = 0.0
        self._next_grid = 0.0
        self._next_cmd = 0.0
        self.started = False

    # ---- lifecycle ----
    def start(self) -> None:
        """Call from inside a running asyncio loop (the Station broadcasts through it)."""
        self.station.loop = asyncio.get_running_loop()
        self.started = True

    def connect(self, cid: str) -> FakeClient:
        """A page opened: what the WebSocket handler sends first."""
        c = FakeClient()
        self.clients[cid] = c
        self.station.clients[cid] = c
        c.queue.append(json.dumps({**self.station.world_msg(with_history=True), "you": cid}))
        if self.station.last_tlm:
            c.queue.append(json.dumps(self.station.last_tlm))
        return c

    def handle(self, cid: str, msg: dict):
        """A message from the page (the same ones a browser sends the station). Returns the
        awaitable (Station.handle is async: a sweep waits a beat for the boat's ack)."""
        return asyncio.ensure_future(self.station.handle(cid, msg))

    def handle_json(self, cid: str, raw: str):
        return self.handle(cid, json.loads(raw))

    def drain(self, cid: str) -> list[str]:
        c = self.clients.get(cid)
        if not c:
            return []
        out, c.queue = c.queue, []
        return out

    # ---- the clock ----
    def step(self) -> None:
        """Advance everything to now. Call ~20 times a second."""
        now = time.time()
        dt = min(0.25, max(0.0, now - self._last_step))
        self._last_step = now
        self.phys.step(dt)
        self.ard.update(now)
        self.boat.link.step(now)
        self.station.link.step(now)
        if now >= self._next_tick:                      # the Pi's 10 Hz loop
            self._next_tick = now + 1.0 / boat_config.LOOP_HZ
            self.boat.tick(now)
            if now >= self._next_tlm - 0.05:
                self._next_tlm = now + 1.0 / boat_config.TELEMETRY_HZ
                self.boat.telemetry(now)
        if now >= self._next_cmd:                       # the station's 10 Hz cmd
            self._next_cmd = now + 1.0 / station_config.CMD_HZ
            self.station.cmd_tick()
        if self.started and now >= self._next_grid:     # the map every 2 s
            self._next_grid = now + 2.0
            asyncio.ensure_future(self.station.grid_tick())

    # ---- sim-only ground truth, same shape as fake_arduino's /truth ----
    def truth(self) -> dict:
        p = self.phys
        return {
            "t": round(p.t, 2), "total": p.trash_total, "collected": p.collected_count,
            "trash": [{"id": tp.id, "lat": round(p.world_to_latlon(tp.x, tp.y)[0], 6), "lon": round(p.world_to_latlon(tp.x, tp.y)[1], 6),
                       "kind": tp.kind, "collected": tp.collected, "collected_t": tp.collected_t} for tp in p.trash],
            "boat": {"lat": round(p.world_to_latlon(p.x, p.y)[0], 6), "lon": round(p.world_to_latlon(p.x, p.y)[1], 6),
                     "heading_deg": round(p.heading_deg, 1), "moored": p.moored},
        }

    def truth_json(self) -> str:
        return json.dumps(self.truth())

    def export_csv(self) -> str:
        import csv
        import io
        rows = self.station.db.tlm_rows()
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=rows[0].keys() if rows else ["ts"])
        w.writeheader()
        w.writerows(rows)
        return buf.getvalue()
