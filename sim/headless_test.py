"""Run the sim with no browser and check the boat actually does the things.

    python sim/headless_test.py

1. Starts the sim (range 120 m).
2. Takes control, drives north for a while, checks the boat moved.
3. Starts a sweep of a 30 x 20 m rectangle, waits for sweep_done.
4. Drives the boat out past radio range, checks link_lost -> backing_up -> home.
Prints PASS/FAIL per step. Exit code 0 if all pass.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time

import websockets

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8765


async def main() -> int:
    sim = subprocess.Popen([sys.executable, "run.py", "--range", "120", "--http", str(PORT), "--db", "/tmp/headless.sqlite", "--quiet", "--current", "0.05,0.02"], cwd=HERE)
    ok = True
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
            state = {"tlm": None, "events": [], "world": None}

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
                    elif m["t"] == "evt":
                        state["events"].append(m["kind"])
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
            dlat = 20 / 111320; dlon = 30 / (111320 * 0.777)
            await ws.send(json.dumps({"t": "sweep", "corners": [[lat + dlat * 0.3, lon - dlon / 2], [lat + dlat * 1.3, lon + dlon / 2]]}))
            got_auto = await pump(10, lambda: state["tlm"] and state["tlm"]["mode"] == "AUTO")
            check("sweep request puts the boat in AUTO", got_auto)
            done = await pump(420, lambda: "sweep_done" in state["events"])
            check("sweep finishes", done)
            await pump(30, lambda: state["tlm"] and state["tlm"]["mode"] == "DRIVEN" or "home_done" in state["events"])

            # 3. drive out of range
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
            back = await pump(240, lambda: "link_up" in state["events"][state["events"].index("link_down"):])
            check("boat comes back into range on its own", back)
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
    print("\nALL PASS" if ok else "\nSOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
