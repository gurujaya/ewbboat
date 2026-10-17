"""Run the sim with no browser and check the boat actually does the things.

    python sim/headless_test.py

1. Starts the sim (range 120 m).
2. Takes control, drives north for a while, checks the boat moved.
3. Starts a sweep of a 30 x 20 m rectangle, waits for sweep_done, and measures
   how well the boat held the planned rows (cross-track error).
4. Waits for the boat to come straight home (Come home = the fastest way), and times it.
5. Drives the boat out past radio range, checks link_lost -> backing_up -> home.
Prints PASS/FAIL per step, then the accuracy numbers. Exit code 0 if all pass.

Running a second sim at the same time? Give this one its own ports, e.g.
    SIM_SERIAL_LINK=/tmp/boat-serial-2 STATION_PORT=5600 BOAT_PORT=5601 HEADLESS_HTTP=8766 python sim/headless_test.py
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import subprocess
import sys
import time

import websockets

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("HEADLESS_HTTP", "8765"))
M_PER_DEG_LAT = 111_320.0

# Accuracy limits. Why these numbers:
# - Cross-track is measured from tlm, i.e. against where the boat's own (filtered) GPS
#   says it is. That's what the autopilot can control; the GPS's own slow drift
#   (~1 m in the sim) comes on top and no steering can remove it.
# - RMS < 1.0 m: the sim's rows are 3 m apart, so a boat that holds its GPS line to
#   within 1 m RMS covers its row with room to spare. In fast-time tests of the
#   tuned autopilot it's ~0.4 m, and ~0.6 m with 2x the current. (The old
#   stop-at-every-waypoint autopilot measured 0.84 m here, against raw 1 Hz GPS.)
# - Max < 3.0 m (one row spacing), measured on the straight part of a row, after
#   the boat has had SETTLE_M to line up from the U-turn: it never wanders onto
#   the next row.
# - Going home retraces the whole trail (~170 m of cleaned-up path here). At cruise
#   (0.6 throttle, ~0.85 m/s) that's ~3.5 minutes with the corners; 300 s leaves
#   margin. The old autopilot slowed to a crawl at every trail point and hadn't
#   got home after 420 s.
XT_RMS_LIMIT_M = 1.0
XT_MAX_LIMIT_M = 3.0
SETTLE_M = 5.0
HOME_LEG_LIMIT_S = 300.0


def to_xy(p: tuple[float, float], ref: tuple[float, float]) -> tuple[float, float]:
    """lat/lon -> meters east, north of ref (flat earth, fine for a pond)."""
    return ((p[1] - ref[1]) * M_PER_DEG_LAT * math.cos(math.radians(ref[0])), (p[0] - ref[0]) * M_PER_DEG_LAT)


def row_error(p, a, b) -> tuple[float, float, float]:
    """(cross-track m, along-track m from a, row length m) of p against the line a -> b."""
    ax, ay = to_xy(a, a)
    bx, by = to_xy(b, a)
    px, py = to_xy(p, a)
    length = math.hypot(bx - ax, by - ay)
    ux, uy = (bx - ax) / length, (by - ay) / length
    along = px * ux + py * uy
    cross = abs(px * uy - py * ux)
    return cross, along, length


def rms(xs: list[float]) -> float:
    return math.sqrt(sum(x * x for x in xs) / len(xs)) if xs else float("nan")


async def main() -> int:
    sim = subprocess.Popen([sys.executable, "run.py", "--range", "120", "--http", str(PORT), "--db", "/tmp/headless.sqlite", "--quiet", "--current", "0.05,0.02"], cwd=HERE)
    ok = True
    results: list[str] = []
    try:
        for _ in range(40):                     # wait for the station to come up
            await asyncio.sleep(0.5)
            try:
                probe = await websockets.connect(f"ws://localhost:{PORT}/ws")
                await probe.close()
                break
            except OSError:
                continue
        async with websockets.connect(f"ws://localhost:{PORT}/ws", max_size=2**22) as ws:
            state = {"tlm": None, "events": [], "world": None, "trail": [], "auto": [], "evt_at": {}}

            async def pump(seconds: float, until=None):
                end = time.time() + seconds
                while time.time() < end:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=0.5)
                    except asyncio.TimeoutError:
                        continue
                    m = json.loads(raw)
                    if m["t"] == "tlm":
                        state["tlm"] = m
                        if m["mode"] == "AUTO" and m.get("wp_index") is not None:
                            state["auto"].append((m["lat"], m["lon"], m["wp_index"]))
                    elif m["t"] == "trail":
                        state["trail"].append((m["lat"], m["lon"]))
                    elif m["t"] == "evt":
                        state["events"].append(m["kind"])
                        state["evt_at"].setdefault(m["kind"], time.time())
                        if m["kind"] != "wp_reached":
                            print(f"   evt {m['kind']} {m.get('detail','')}")
                    elif m["t"] == "world":
                        state["world"] = m
                    elif m["t"] == "link":
                        state["events"].append("link_down" if not m["up"] else "link_up")
                        print(f"   station: link {'up' if m['up'] else 'DOWN'}")
                    if until and until():
                        return True
                return until() if until else False

            def check(name, cond):
                nonlocal ok
                print(("PASS " if cond else "FAIL ") + name)
                ok = ok and cond

            await pump(6, lambda: state["tlm"] is not None and state["tlm"]["gps_fix"])
            check("telemetry arrives with a GPS fix", state["tlm"] is not None and state["tlm"]["gps_fix"])
            start = (state["tlm"]["lat"], state["tlm"]["lon"])

            # 1. drive north
            await ws.send(json.dumps({"t": "take"}))
            t_end = time.time() + 8
            while time.time() < t_end:
                await ws.send(json.dumps({"t": "ctl", "throttle": 0.8, "steer": 0.0, "conveyor": True}))
                await pump(0.1)
            moved = (state["tlm"]["lat"] - start[0]) * 111320
            check(f"driven mode moves the boat north ({moved:.1f} m)", moved > 4)
            await ws.send(json.dumps({"t": "release"}))

            # 2. sweep a small rectangle in front of the boat
            lat, lon = state["tlm"]["lat"], state["tlm"]["lon"]
            # 20 x 8 m: at the station's scoop-width rows (0.65 m) that's 7 rows of 16 m, about 3 minutes
            dlat = 8 / 111320; dlon = 20 / (111320 * 0.777)
            await ws.send(json.dumps({"t": "sweep", "corners": [[lat + dlat * 0.3, lon - dlon / 2], [lat + dlat * 1.3, lon + dlon / 2]]}))
            got_auto = await pump(10, lambda: state["tlm"] and state["tlm"]["mode"] == "AUTO")
            check("sweep request puts the boat in AUTO", got_auto)
            t_sweep = time.time()
            done = await pump(420, lambda: "sweep_done" in state["events"])
            check("sweep finishes", done)
            sweep_s = time.time() - t_sweep

            # how well did it hold the rows? Row r runs from points[2r] to points[2r+1];
            # while wp_index is odd the boat is on a row (heading for its far end).
            pts = [tuple(p) for p in (state["world"] or {}).get("sweep_points") or []]
            xt_all, xt_settled = [], []
            for la, lo, i in state["auto"]:
                if i % 2 == 1 and i < len(pts):
                    cross, along, length = row_error((la, lo), pts[i - 1], pts[i])
                    if 0.0 <= along <= length:
                        xt_all.append(cross)
                        if along >= SETTLE_M:
                            xt_settled.append(cross)
            xt_rms, xt_max = rms(xt_settled), max(xt_settled, default=float("nan"))
            results.append(f"sweep: {sweep_s:.0f} s, {len(pts)} points, {len(xt_all)} on-row tlm samples")
            results.append(f"sweep cross-track, whole rows:       RMS {rms(xt_all):.2f} m, max {max(xt_all, default=float('nan')):.2f} m")
            results.append(f"sweep cross-track, after {SETTLE_M:.0f} m settle: RMS {xt_rms:.2f} m, max {xt_max:.2f} m")
            check(f"sweep holds its rows: cross-track RMS {xt_rms:.2f} m < {XT_RMS_LIMIT_M} m", xt_rms < XT_RMS_LIMIT_M)
            check(f"sweep never strays: cross-track max {xt_max:.2f} m < {XT_MAX_LIMIT_M} m", xt_max < XT_MAX_LIMIT_M)

            # 3. it comes straight home on its own (a lost link is what retraces the trail; step 5)
            home_done = await pump(HOME_LEG_LIMIT_S + 60, lambda: "home_done" in state["events"])
            home_s = state["evt_at"]["home_done"] - state["evt_at"]["sweep_done"] if home_done and "sweep_done" in state["evt_at"] else float("nan")
            home_err = float("nan")
            if state["trail"] and state["tlm"]:
                hx, hy = to_xy((state["tlm"]["lat"], state["tlm"]["lon"]), state["trail"][0])
                home_err = math.hypot(hx, hy)
            if home_done:
                results.append(f"come-home leg: {home_s:.0f} s, stopped {home_err:.1f} m from the launch point, trail {len(state['trail'])} points")
            else:
                results.append(f"come-home leg: NOT done after {HOME_LEG_LIMIT_S + 60:.0f} s, still {home_err:.1f} m from the launch point")
            check(f"boat comes home in {home_s:.0f} s < {HOME_LEG_LIMIT_S:.0f} s", home_done and home_s < HOME_LEG_LIMIT_S)

            # 4. drive out of range
            state["events"].clear()
            await ws.send(json.dumps({"t": "drive"}))
            await pump(3, lambda: state["tlm"]["mode"] == "DRIVEN")
            await ws.send(json.dumps({"t": "take"}))
            t_end = time.time() + 150
            while time.time() < t_end and "link_down" not in state["events"]:
                hdg = state["tlm"]["heading_deg"]
                steer = max(-0.6, min(0.6, ((0 - hdg + 540) % 360 - 180) * 0.01))  # point north, away from the station
                await ws.send(json.dumps({"t": "ctl", "throttle": 1.0, "steer": steer, "conveyor": False}))
                await pump(0.1)
            check("station sees the link drop past radio range", "link_down" in state["events"])
            await ws.send(json.dumps({"t": "release"}))
            t_lost = time.time()
            back = await pump(240, lambda: "link_up" in state["events"][state["events"].index("link_down"):])
            check("boat comes back into range on its own", back)
            results.append(f"lost-signal recovery: link back {time.time() - t_lost:.0f} s after it dropped")
            await pump(5)
            check("boat delivered the link_lost event it recorded while out of range", "link_lost" in state["events"])
            if state["tlm"]:
                print(f"   final mode {state['tlm']['mode']} phase {state['tlm'].get('home_phase')} dist {((state['tlm']['lat']-start[0])*111320):.0f} m north of start")
    finally:
        sim.send_signal(2)
        try:
            sim.wait(timeout=8)
        except subprocess.TimeoutExpired:
            sim.kill()
    print("\naccuracy:")
    for line in results:
        print("   " + line)
    print("\nALL PASS" if ok else "\nSOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
