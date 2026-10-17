"""The browser demo's core (sim/browser/core.py) under plain CPython: the real Boat and
Station classes wired to the in-memory fakes, driven on a real clock for a few seconds."""

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "browser"))

from core import BrowserSim  # noqa: E402


def _msgs(sim, cid):
    return [json.loads(s) for s in sim.drain(cid)]


async def _run(sim, seconds, cid, kinds):
    """Step the sim in real time for `seconds`, collecting messages of the given types."""
    got = []
    end = time.time() + seconds
    while time.time() < end:
        sim.step()
        await asyncio.sleep(0.04)
        got += [m for m in _msgs(sim, cid) if m["t"] in kinds]
    return got


def test_boat_and_station_run_in_one_process():
    async def main():
        sim = BrowserSim(trash=10)
        sim.start()
        c = sim.connect("tab1")
        first = _msgs(sim, "tab1")
        assert first and first[0]["t"] == "world" and first[0]["you"] == "tab1"
        assert first[0]["fence_radius_m"] == 150.0

        # telemetry flows at ~5 Hz through the fake radio, with the link up on both sides
        tlm = await _run(sim, 2.0, "tab1", {"tlm"})
        assert len(tlm) >= 7, len(tlm)
        assert tlm[-1]["mode"] == "DRIVEN" and tlm[-1]["gps_fix"]
        assert sim.boat.link.up and sim.station.link.up

        # the boat is tied up at the jetty until someone drives: it stays put
        start = (tlm[-1]["lat"], tlm[-1]["lon"])
        assert sim.phys.moored

        # a tab takes control and drives north with the belt on: the boat moves, the belt runs
        await sim.handle("tab1", {"t": "take"})
        for _ in range(8):                                  # a stick sends ~10 times a second; 2 is enough here
            await sim.handle("tab1", {"t": "ctl", "throttle": 0.8, "steer": 0.0, "conveyor": True})
            tlm = await _run(sim, 0.5, "tab1", {"tlm"}) or tlm
        moved_m = (tlm[-1]["lat"] - start[0]) * 111320
        assert moved_m > 1.0, moved_m
        assert tlm[-1]["conveyor"] is True
        assert not sim.phys.moored

        # Home: straight home (DIRECT), the operator's request answered by the real Modes rules
        await sim.handle("tab1", {"t": "home"})
        msgs = await _run(sim, 1.5, "tab1", {"tlm", "ack", "evt"})
        assert any(m["t"] == "tlm" and m["mode"] == "COMING_HOME" and m["home_phase"] == "DIRECT" for m in msgs)
        assert any(m["t"] == "evt" and m["kind"] == "mode_change" for m in msgs)

        # sim-only truth: the litter is there, and the CSV export has rows
        truth = sim.truth()
        assert truth["total"] == 10 and len(truth["trash"]) == 10
        assert sim.export_csv().count("\n") > 5

    asyncio.run(main())
