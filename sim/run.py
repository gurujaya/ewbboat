"""Start the whole system on one laptop, no hardware.

    python sim/run.py                      # defaults: gentle current, 200 m radio range
    python sim/run.py --range 120 --current 0.3,0.1 --noise 3
    python sim/run.py --drain 20           # battery dies in a few minutes: watch the rules fire

Then open http://localhost:8000/viewer

Three processes, exactly like the real boat: the fake Arduino (a pty), the real
boat-pi code, the real ground station. Ctrl-C stops all of them.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
PY = sys.executable


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--range", type=float, default=200.0, help="radio range in m (signal hits -88 dBm here)")
    ap.add_argument("--current", default="0.15,0.05", help="water current east,north m/s")
    ap.add_argument("--noise", type=float, default=1.5, help="GPS noise std dev, m")
    ap.add_argument("--start", default="0,15", help="boat start x,y m from the station")
    ap.add_argument("--batt", type=float, default=12.6)
    ap.add_argument("--drain", type=float, default=1.0, help="battery drain multiplier")
    ap.add_argument("--http", type=int, default=8000)
    ap.add_argument("--db", default="/tmp/station-sim.sqlite")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    link = "/tmp/boat-serial"
    env = dict(os.environ, BOAT_ENV="sim", BOAT_SERIAL=link, HTTP_PORT=str(args.http), STATION_DB=args.db, BOAT_LOG_DIR="/tmp/boat-logs", PYTHONUNBUFFERED="1")
    out = subprocess.DEVNULL if args.quiet else None

    procs: list[subprocess.Popen] = []

    def start(name, cmd, cwd):
        p = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT if args.quiet else None)
        procs.append(p)
        print(f"[sim] started {name} (pid {p.pid})", flush=True)
        return p

    try:
        start("fake arduino", [PY, "fake_arduino.py", "--link", link, "--current", args.current, "--range", str(args.range),
                               "--noise", str(args.noise), "--start", args.start, "--batt", str(args.batt), "--drain", str(args.drain)], HERE)
        for _ in range(50):
            if os.path.islink(link):
                break
            time.sleep(0.1)
        start("ground station", [PY, "main.py"], os.path.join(ROOT, "ground-station"))
        time.sleep(0.8)
        start("boat pi", [PY, "main.py"], os.path.join(ROOT, "boat-pi"))
        print(f"\n[sim] open http://localhost:{args.http}/viewer   (Ctrl-C to stop)\n", flush=True)
        while True:
            for p in procs:
                if p.poll() is not None:
                    print(f"[sim] a process exited with {p.returncode}; stopping", flush=True)
                    return
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is None:
                p.send_signal(signal.SIGTERM)
        for p in procs:
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
        print("[sim] stopped", flush=True)


if __name__ == "__main__":
    main()
