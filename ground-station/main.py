"""The ground station. Always on. Saves everything, serves everyone.

    python main.py            # http://localhost:8000  (dashboard)  /viewer (3D sim view)

Link to the boat on a thread (comms/boatlink), FastAPI + WebSocket on asyncio.
Every message from the boat: save to SQLite, then push to every browser.
Browsers send small control messages back; the station turns them into `cmd`.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "comms"))

import uvicorn
from boatlink import Link
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

import config
from db import DB
from grid import Grid
from sweep import corners_inside_circle, plan

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("station")

HERE = os.path.dirname(os.path.abspath(__file__))
DASHBOARD = os.path.join(HERE, "..", "dashboard")
VIEWER = os.path.join(HERE, "..", "sim", "viewer")


def driven_fence(origin, r_m):
    dlat = r_m / 111_320.0
    dlon = r_m / (111_320.0 * __import__("math").cos(__import__("math").radians(origin[0])))
    return [[origin[0] - dlat, origin[1] - dlon], [origin[0] + dlat, origin[1] + dlon]]


class Station:
    def __init__(self) -> None:
        self.db = DB(config.DB_PATH)
        self.grid = Grid(config.ORIGIN, config.GRID_M)
        self.link = Link("station", listen=config.STATION_LISTEN, peer=config.BOAT_ADDR)
        self.loop: asyncio.AbstractEventLoop | None = None
        self.clients: dict[str, WebSocket] = {}
        self.holder: str | None = None
        self.last_tlm: dict | None = None
        self.ctl = {"throttle": 0.0, "steer": 0.0, "conveyor": False}
        self.ctl_at = 0.0
        self.seq = 0
        self.want_mode: str | None = None
        self.want_until = 0.0
        self.sweep_corners: list | None = None
        self.sweep_points: list | None = None
        self.events: list[dict] = []
        for t in ("tlm", "trail", "evt", "ack", "hb"):
            self.link.on(t, self.from_boat)
        self.link.on_link_lost(lambda: self.push({"t": "link", "up": False, "ts": time.time()}))
        self.link.on_link_back(lambda: self.push({"t": "link", "up": True, "ts": time.time()}))

    # ---- from the boat (link thread) ------------------------------------------
    def from_boat(self, m: dict) -> None:
        if m["t"] == "hb":
            return
        self.db.save(m)
        if m["t"] == "tlm":
            self.last_tlm = m
            if m.get("gps_fix"):
                self.grid.reading(m["lat"], m["lon"], m.get("water"))
                # "covered" = the belt went over it: the strip under the boat while the conveyor runs
                if m.get("conveyor") and m.get("heading_deg") is not None:
                    self.grid.mark_swath(m["lat"], m["lon"], m["heading_deg"], config.SCOOP_WIDTH_M)
        elif m["t"] == "evt":
            self.events.append(m)
            self.events = self.events[-200:]
        elif m["t"] == "ack" and m.get("for") == "mode":
            # the boat answered the mode request (yes or no); stop repeating it,
            # otherwise one button press earns three identical refusals
            self.want_mode = None
        self.push(m)

    def push(self, m: dict) -> None:
        if self.loop:
            self.loop.call_soon_threadsafe(lambda: asyncio.ensure_future(self.broadcast(m)))

    async def broadcast(self, m: dict) -> None:
        data = json.dumps(m)
        dead = []
        for cid, ws in self.clients.items():
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(cid)
        for cid in dead:
            self.clients.pop(cid, None)
            if self.holder == cid:
                self.holder = None

    # ---- to the boat --------------------------------------------------------------
    def world_msg(self, with_history: bool = False) -> dict:
        # event history only goes to a browser that just connected; re-sending it on every
        # world update made each open page show every old event twice
        return {
            "t": "world", "ts": time.time(), "origin": config.ORIGIN, "grid_m": config.GRID_M,
            "fence_driven": driven_fence(config.ORIGIN, config.DRIVEN_FENCE_M),
            "fence_radius_m": config.DRIVEN_FENCE_M,   # the boat enforces a circle this big around ORIGIN
            "sweep_corners": self.sweep_corners, "sweep_points": self.sweep_points,
            "holder": self.holder, "events": self.events[-50:] if with_history else [], "link_up": self.link.up,
        }

    def request_mode(self, mode: str) -> None:
        self.want_mode = mode
        self.want_until = time.time() + 5.0

    async def cmd_loop(self) -> None:
        while True:
            await asyncio.sleep(1.0 / config.CMD_HZ)
            if not self.link.up:
                continue
            now = time.time()
            asking = self.want_mode is not None and now < self.want_until
            mode = self.want_mode if asking else (self.last_tlm or {}).get("mode", "DRIVEN")
            fresh = now - self.ctl_at < 1.0 and self.holder is not None
            self.seq += 1
            self.link.send("cmd", {
                "seq": self.seq,
                "throttle": self.ctl["throttle"] if fresh else 0.0,
                "steer": self.ctl["steer"] if fresh else 0.0,
                "conveyor": self.ctl["conveyor"] if fresh else False,
                "mode": mode,
                "ask": asking,
            })

    async def grid_loop(self) -> None:
        while True:
            await asyncio.sleep(2.0)
            snap = self.grid.snapshot()
            snap["t"] = "grid"
            snap["ts"] = time.time()
            snap["coverage_pct"] = self.grid.coverage_pct(self.sweep_corners)
            await self.broadcast(snap)

    # ---- from browsers ---------------------------------------------------------------
    async def handle(self, cid: str, m: dict) -> None:
        t = m.get("t")
        if t == "take":
            # Take control means "a person steers" (ARCHITECTURE.md, Modes), so it also asks for DRIVEN.
            # The boat still decides; from AUTO or COMING_HOME this is how the operator gets the wheel back.
            self.holder = cid
            self.request_mode("DRIVEN")
            await self.broadcast({"t": "control", "holder": cid, "ts": time.time()})
        elif t == "release" and self.holder == cid:
            self.holder = None
            await self.broadcast({"t": "control", "holder": None, "ts": time.time()})
        elif t == "ctl" and self.holder == cid:
            self.ctl = {"throttle": float(m.get("throttle", 0)), "steer": float(m.get("steer", 0)), "conveyor": bool(m.get("conveyor", False))}
            self.ctl_at = time.time()
        elif t == "drive":
            self.request_mode("DRIVEN")
        elif t == "home":
            self.request_mode("COMING_HOME")
        elif t == "sweep":
            corners = [[float(p[0]), float(p[1])] for p in m["corners"]]
            # the station says no before the boat ever hears about it: a rectangle outside the
            # driving fence would take the boat out of radio range on purpose
            if not corners_inside_circle([tuple(c) for c in corners], config.ORIGIN, config.DRIVEN_FENCE_M):
                await self.clients[cid].send_text(json.dumps({"t": "ack", "for": "sweep", "ok": False, "ts": time.time(),
                                                              "msg": f"the rectangle reaches outside the {config.DRIVEN_FENCE_M:.0f} m fence; draw it closer to the station"}))
                return
            pts = plan([tuple(c) for c in corners], config.ROW_SPACING_M, turn_rows=config.SWEEP_TURN_ROWS)
            if len(pts) < 2:
                await self.clients[cid].send_text(json.dumps({"t": "ack", "for": "sweep", "ok": False, "ts": time.time(), "msg": "the rectangle is too small for a row"}))
                return
            sid = f"sweep-{uuid.uuid4().hex[:6]}"
            self.sweep_corners, self.sweep_points = corners, pts
            self.db.save_sweep(sid, corners, pts)
            self.link.send("wps", {"id": sid, "points": pts})
            await asyncio.sleep(0.3)          # give the boat a beat to ack
            self.request_mode("AUTO")
            await self.broadcast(self.world_msg())
        elif t == "trash":
            if self.last_tlm:
                self.grid.trash.append([self.last_tlm["lat"], self.last_tlm["lon"]])
                await self.broadcast({"t": "evt", "kind": "trash_marked", "ts": time.time(), "detail": ""})


station = Station()
app = FastAPI()


@app.middleware("http")
async def no_stale_pages(request, call_next):
    # the page and its scripts change while we develop; make browsers check every time
    # instead of quietly running yesterday's copy of the JS
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    cid = uuid.uuid4().hex[:8]
    station.clients[cid] = ws
    await ws.send_text(json.dumps({**station.world_msg(with_history=True), "you": cid}))
    if station.last_tlm:
        await ws.send_text(json.dumps(station.last_tlm))
    try:
        while True:
            raw = await ws.receive_text()
            try:
                await station.handle(cid, json.loads(raw))
            except Exception:
                log.exception("bad browser message")
    except WebSocketDisconnect:
        pass
    finally:
        station.clients.pop(cid, None)
        if station.holder == cid:
            station.holder = None
            await station.broadcast({"t": "control", "holder": None, "ts": time.time()})


@app.get("/api/export.csv")
def export_csv():
    rows = station.db.tlm_rows()
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=rows[0].keys() if rows else ["ts"])
    w.writeheader()
    w.writerows(rows)
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=run.csv"})


@app.get("/api/events")
def events():
    return station.events[-200:]


@app.get("/api/grid")
def grid():
    return station.grid.snapshot()


# SIM ONLY. The simulator's fake Arduino serves a "ground truth" feed (where the litter really is,
# what the belt really scooped) on its own port. On a laptop the viewer reads it directly; on a
# public demo host only this port is reachable, so the station passes it through. sim/run.py sets
# SIM_TRUTH_URL; on the real station it's unset and this route says so with a 404.
SIM_TRUTH_URL = os.environ.get("SIM_TRUTH_URL", "")


@app.get("/api/sim/truth")
def sim_truth():
    if not SIM_TRUTH_URL:
        return Response("not a simulation", status_code=404)
    import urllib.request
    try:
        with urllib.request.urlopen(SIM_TRUTH_URL, timeout=0.5) as r:
            return Response(r.read(), media_type="application/json", headers={"Cache-Control": "no-store"})
    except Exception:
        return Response("truth feed unavailable", status_code=503)


@app.get("/viewer")
def viewer():
    return FileResponse(os.path.join(VIEWER, "index.html"))


app.mount("/viewer", StaticFiles(directory=VIEWER), name="viewer")
if os.path.isfile(os.path.join(DASHBOARD, "index.html")):
    app.mount("/", StaticFiles(directory=DASHBOARD, html=True), name="dashboard")
else:
    @app.get("/")
    def root():
        return Response("<a href='/viewer'>3D viewer</a> &middot; dashboard not built yet", media_type="text/html")


@app.on_event("startup")
async def startup():
    station.loop = asyncio.get_running_loop()
    station.link.start()
    asyncio.ensure_future(station.cmd_loop())
    asyncio.ensure_future(station.grid_loop())
    log.info("station up: boat=%s http=%s db=%s", config.BOAT_ADDR, config.HTTP_PORT, config.DB_PATH)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=config.HTTP_PORT, log_level="warning")
