"""The Arduino end of the simulator: real firmware logic, fake world.

    python fake_arduino.py --link /tmp/boat-serial [--current 0.2,0.1] [--range 200] [--noise 1.5]

The decisions the Arduino makes (parsing M lines, the 2 s watchdog, battery
warnings and the 10 % motor cut, building T and E lines) are NOT written here.
They run inside boat-arduino/build/boat-host, which is the firmware's own C++
(boat-arduino/boat/src/) compiled for the laptop. sim/run.py builds it.

This file only does what the board's pins and the lake would do:
  - owns the pty that boat-pi opens as its "USB serial port" (symlink at --link)
  - passes every byte the Pi writes to the firmware ("rx" lines)
  - every 50 ms, gives the firmware sensor readings from physics.py ("tick")
    and gets back what it wrote to serial ("tx") and its motor outputs ("out")
  - writes the firmware's serial output to the pty, and moves the boat with
    the motor outputs
  - adds the sim-only `S <dbm>` line (radio signal; that's not the Arduino's
    job, so it stays in Python)
  - serves the sim-only "ground truth" (where the trash and the boat REALLY
    are) as JSON on http://localhost:8099/truth, for the 3D viewer to draw

The host protocol is described at the top of boat-arduino/host/host_main.cpp.
"""

from __future__ import annotations

import argparse
import json
import os
import pty
import select
import signal
import subprocess
import sys
import threading
import time
import tty
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from physics import BoatPhysics, World

HERE = os.path.dirname(os.path.abspath(__file__))
HOST_BIN = os.path.join(HERE, "..", "boat-arduino", "build", "boat-host")

TICK_S = 0.05        # one firmware step + physics step every 50 ms (20 Hz)
GPS_EVERY_S = 0.2    # 5 fixes a second, like a u-blox M8N set to 5 Hz (the firmware sends T lines at 5 Hz too)
SIGNAL_EVERY_S = 1.0
TRUTH_EVERY_S = 0.1  # how often the ground-truth snapshot is refreshed (10 Hz is plenty for drawing)


class TruthServer:
    """SIM ONLY. A tiny HTTP server that hands out the lake's ground truth: the
    TRUE position of every piece of trash, which ones are in the basket, and
    the TRUE boat position and heading (not the noisy GPS, not the compass).

    The real boat cannot know any of this; nothing in boat-pi or the ground
    station reads it, and it must stay that way. The viewer uses it only to draw
    the litter on the water and show a "collected" count, so the demo visibly
    picks something up.

    The physics loop calls update() with a fresh snapshot; requests are served
    from that snapshot under a lock, on their own daemon threads. A problem in
    here (port busy, a client hanging up) must never stop the physics loop.
    """

    def __init__(self, port: int):
        self.port = port
        self._lock = threading.Lock()
        self._body = b'{"t": 0, "total": 0, "collected": 0, "trash": [], "boat": null}'
        self.url = ""
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path.split("?")[0] != "/truth":
                    self.send_error(404)
                    return
                with server._lock:
                    body = server._body
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                # The viewer is served by the station on another port: let the browser fetch across ports.
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_) -> None:
                pass   # one line per poll would bury the real output

        try:
            self._httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
            self._httpd.daemon_threads = True
            threading.Thread(target=self._httpd.serve_forever, daemon=True, name="truth-http").start()
            self.url = f"http://localhost:{port}/truth"
        except OSError as e:
            self._httpd = None
            print(f"[fake arduino] ground-truth server not started on port {port}: {e}", file=sys.stderr, flush=True)

    def update(self, boat: BoatPhysics) -> None:
        """Take a snapshot of the lake. Called from the physics loop; cheap."""
        try:
            pieces = []
            for p in boat.trash:
                lat, lon = boat.world_to_latlon(p.x, p.y)
                pieces.append({"id": p.id, "lat": round(lat, 6), "lon": round(lon, 6), "kind": p.kind,
                               "collected": p.collected, "collected_t": None if p.collected_t is None else round(p.collected_t, 2)})
            blat, blon = boat.world_to_latlon(boat.x, boat.y)
            snap = {
                "t": round(boat.t, 2),
                "total": boat.trash_total,
                "collected": boat.collected_count,
                "trash": pieces,
                "boat": {"lat": round(blat, 6), "lon": round(blon, 6), "heading_deg": round(boat.heading_deg, 1), "moored": boat.moored},
            }
            body = json.dumps(snap).encode()
            with self._lock:
                self._body = body
        except Exception as e:   # never let the viewer's feed take the lake down
            print(f"[fake arduino] ground-truth snapshot failed: {e}", file=sys.stderr, flush=True)

    def close(self) -> None:
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:
                pass


class Firmware:
    """The compiled firmware, running as a child process we talk to by text lines."""

    def __init__(self, path: str):
        if not os.path.exists(path):
            sys.exit(f"[fake arduino] {path} not found; start the sim with `python sim/run.py`, which builds it")
        self.proc = subprocess.Popen([path], stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def rx(self, ms: int, data: bytes) -> None:
        """Bytes the Pi wrote to the serial port."""
        self._send(f"rx {ms} {data.hex()}\n")

    def tick(self, ms: int, readings: list[float | int]) -> tuple[bytes, tuple[float, float, bool]]:
        """One firmware step. Returns (bytes it wrote to serial, motor outputs)."""
        self._send("tick " + " ".join([str(ms)] + [str(v) for v in readings]) + "\n")
        tx = b""
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("firmware host exited")
            parts = line.split()
            if parts[0] == b"tx":
                tx += bytes.fromhex(parts[1].decode())
            elif parts[0] == b"out":
                return tx, (float(parts[1]), float(parts[2]), parts[3] == b"1")

    def _send(self, text: str) -> None:
        self.proc.stdin.write(text.encode())
        self.proc.stdin.flush()

    def close(self) -> None:
        try:
            self.proc.stdin.close()   # the host exits when its input closes
            self.proc.wait(timeout=2)
        except Exception:
            self.proc.kill()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--link", default="/tmp/boat-serial")
    ap.add_argument("--current", default="0.05,0.02", help="east,north m/s")
    ap.add_argument("--range", type=float, default=200.0, help="radio range, m")
    ap.add_argument("--noise", type=float, default=1.5, help="gps noise, m")
    ap.add_argument("--start", default="4.5,9.5", help="start x,y m from station (default: alongside the jetty)")
    ap.add_argument("--batt", type=float, default=12.6, help="starting volts")
    ap.add_argument("--drain", type=float, default=1.0, help="battery drain multiplier")
    ap.add_argument("--trash", type=int, default=30, help="floating pieces of trash at the start (0 = none)")
    ap.add_argument("--truth-port", type=int, default=8099, help="sim-only ground-truth HTTP port (0 = off)")
    args = ap.parse_args()

    cx, cy = (float(v) for v in args.current.split(","))
    sx, sy = (float(v) for v in args.start.split(","))
    world = World(current_mps=(cx, cy), gps_noise_m=args.noise, radio_range_m=args.range, start_xy=(sx, sy),
                  trash_count=max(0, args.trash))
    boat = BoatPhysics(world)
    boat.batt_v = args.batt
    boat.DRAIN_V_PER_S_FULL *= args.drain
    boat.DRAIN_V_PER_S_IDLE *= args.drain

    truth = TruthServer(args.truth_port) if args.truth_port > 0 else None
    if truth is not None and truth.url:
        print(f"fake arduino: {boat.trash_total} pieces of trash on the water, ground truth at {truth.url}", flush=True)

    fw = Firmware(HOST_BIN)

    master, slave = pty.openpty()
    # Raw mode, like a real serial port: no echo, no line editing. (boat-pi's
    # pyserial does this too when it opens the port; this covers the moment
    # before that.)
    tty.setraw(slave)
    slave_path = os.ttyname(slave)
    try:
        os.unlink(args.link)
    except FileNotFoundError:
        pass
    os.symlink(slave_path, args.link)
    print(f"fake arduino on {slave_path} (-> {args.link}), firmware {os.path.abspath(HOST_BIN)}", flush=True)

    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    t0 = time.monotonic()

    def millis() -> int:
        # Like the Arduino's millis(): ms since power-on, a 32-bit counter.
        return int((time.monotonic() - t0) * 1000) & 0xFFFFFFFF

    next_tick = t0
    last_step = t0
    last_gps = -1e9
    last_signal = t0
    last_truth = -1e9
    gps_latlon = boat.gps()
    at_line_start = True   # is the pty between two complete firmware lines?
    try:
        while running:
            r, _, _ = select.select([master], [], [], max(0.0, next_tick - time.monotonic()))
            if r:
                try:
                    data = os.read(master, 4096)
                except OSError:
                    break
                try:
                    fw.rx(millis(), data)
                except BrokenPipeError:
                    break

            now = time.monotonic()
            if now < next_tick:
                continue
            next_tick += TICK_S
            if next_tick < now:          # fell behind (laptop busy): don't try to catch up
                next_tick = now + TICK_S

            # the lake
            boat.step(now - last_step)
            last_step = now

            # what the sensors read right now
            # (half a tick of slack, so a tick that lands a hair early doesn't stretch 200 ms to 250)
            if now - last_gps >= GPS_EVERY_S - TICK_S / 2:
                gps_latlon = boat.gps()
                last_gps = now
            lat, lon = gps_latlon
            temp, ph, turb, cond = boat.water()
            readings = [f"{lat:.7f}", f"{lon:.7f}", f"{boat.compass_deg():.2f}", 1, 9,
                        f"{boat.batt_v:.4f}", f"{temp:.3f}", f"{ph:.3f}", f"{turb:.3f}", f"{cond:.2f}"]

            # the firmware decides
            try:
                tx, (left, right, conveyor) = fw.tick(millis(), readings)
            except (RuntimeError, BrokenPipeError):
                if running:   # not a normal shutdown (Ctrl-C stops the host too)
                    print("[fake arduino] the firmware process stopped", file=sys.stderr, flush=True)
                break
            boat.set_motors(left, right, conveyor)

            # SIM ONLY: refresh the ground-truth snapshot for the viewer
            if truth is not None and now - last_truth >= TRUTH_EVERY_S:
                truth.update(boat)
                last_truth = now

            out = tx
            if out:
                at_line_start = out.endswith(b"\n")
            # The S line is radio, not Arduino. Only slip it in between two
            # whole firmware lines so it can never split one.
            if now - last_signal >= SIGNAL_EVERY_S and at_line_start:
                out += f"S {boat.signal_dbm():.1f}\n".encode()
                last_signal = now
            if out:
                try:
                    os.write(master, out)
                except OSError:
                    break
    finally:
        fw.close()
        if truth is not None:
            truth.close()
        try:
            os.unlink(args.link)
        except FileNotFoundError:
            pass
        os.close(master)
        os.close(slave)


if __name__ == "__main__":
    main()
