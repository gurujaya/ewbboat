"""Start the whole system on one laptop, no hardware.

    python sim/run.py                      # defaults: gentle current, 200 m radio range
    python sim/run.py --range 120 --current 0.3,0.1 --noise 3
    python sim/run.py --drain 20           # battery dies in a few minutes: watch the rules fire

Then open http://localhost:8000/viewer

Three processes, exactly like the real boat: the Arduino (the real firmware
logic compiled for this laptop, behind a pty), the real boat-pi code, the real
ground station. Ctrl-C stops all of them.
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
PY = sys.executable

FIRMWARE = os.path.join(ROOT, "boat-arduino")
FIRMWARE_HOST = os.path.join(FIRMWARE, "build", "boat-host")


def build_firmware_host() -> None:
    """Compile the Arduino firmware's logic (boat-arduino/boat/src) for this laptop.

    Only rebuilds when a source file is newer than the binary, so normally this
    takes no time. Same flags as `make -C boat-arduino host`.
    """
    core_cpp = sorted(glob.glob(os.path.join(FIRMWARE, "boat", "src", "*.cpp")))
    main_cpp = os.path.join(FIRMWARE, "host", "host_main.cpp")
    sources = core_cpp + glob.glob(os.path.join(FIRMWARE, "boat", "src", "*.h")) + [main_cpp]
    if os.path.exists(FIRMWARE_HOST) and os.path.getmtime(FIRMWARE_HOST) >= max(os.path.getmtime(s) for s in sources):
        return
    cxx = os.environ.get("CXX") or shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
    if not cxx:
        sys.exit("[sim] no C++ compiler found, needed to build the Arduino firmware for the sim. "
                 "Install one: macOS `xcode-select --install`, Ubuntu/Debian `sudo apt install g++`.")
    os.makedirs(os.path.dirname(FIRMWARE_HOST), exist_ok=True)
    print("[sim] building the Arduino firmware for this laptop ...", flush=True)
    cmd = [cxx, "-std=c++17", "-O2", "-Wall", "-Wextra", "-o", FIRMWARE_HOST, main_cpp, *core_cpp]
    if subprocess.run(cmd).returncode != 0:
        sys.exit("[sim] the firmware didn't compile (errors above); fix boat-arduino/boat/src first")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--range", type=float, default=200.0, help="radio range in m (signal hits -88 dBm here)")
    ap.add_argument("--current", default="0.05,0.02", help="water current east,north m/s (default: a calm day; 0.15,0.05 is breezy)")
    ap.add_argument("--noise", type=float, default=1.5, help="GPS noise std dev, m")
    ap.add_argument("--start", default="4.5,9.5", help="boat start x,y m from the station (default: alongside the jetty)")
    ap.add_argument("--batt", type=float, default=12.6)
    ap.add_argument("--drain", type=float, default=1.0, help="battery drain multiplier")
    ap.add_argument("--http", type=int, default=int(os.environ.get("PORT", "8000")), help="web port (default $PORT, or 8000); hosts like Render, Cloud Run and Hugging Face set PORT")
    ap.add_argument("--db", default="/tmp/station-sim.sqlite")
    ap.add_argument("--trash", type=int, default=30, help="floating pieces of trash at the start (0 = a clean lake)")
    # The ground-truth feed is sim only (true trash + boat positions for the viewer to draw).
    # Env SIM_TRUTH_PORT sets the default so a second sim can pick its own port like the others.
    ap.add_argument("--truth-port", type=int, default=int(os.environ.get("SIM_TRUTH_PORT", "8099")),
                    help="port for the sim-only ground-truth feed, /truth (0 = off)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    link = os.environ.get("SIM_SERIAL_LINK", "/tmp/boat-serial")   # override to run two sims at once
    env = dict(os.environ, BOAT_ENV="sim", BOAT_SERIAL=link, HTTP_PORT=str(args.http), STATION_DB=args.db, BOAT_LOG_DIR="/tmp/boat-logs", PYTHONUNBUFFERED="1", SIM_TRUTH_URL=(f"http://127.0.0.1:{args.truth_port}/truth" if args.truth_port else ""))
    out = subprocess.DEVNULL if args.quiet else None

    procs: list[subprocess.Popen] = []

    def start(name, cmd, cwd):
        p = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT if args.quiet else None)
        procs.append(p)
        print(f"[sim] started {name} (pid {p.pid})", flush=True)
        return p

    build_firmware_host()

    # `kill` (and `docker stop`) send SIGTERM, not Ctrl-C. Treat it the same so
    # the children are always stopped too, instead of being left running.
    def on_sigterm(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, on_sigterm)

    try:
        start("fake arduino", [PY, "fake_arduino.py", "--link", link, "--current", args.current, "--range", str(args.range),
                               "--noise", str(args.noise), "--start", args.start, "--batt", str(args.batt), "--drain", str(args.drain),
                               "--trash", str(args.trash), "--truth-port", str(args.truth_port)], HERE)
        for _ in range(50):
            if os.path.islink(link):
                break
            time.sleep(0.1)
        start("ground station", [PY, "main.py"], os.path.join(ROOT, "ground-station"))
        time.sleep(0.8)
        start("boat pi", [PY, "main.py"], os.path.join(ROOT, "boat-pi"))
        truth = f"   ground truth (sim only): http://localhost:{args.truth_port}/truth" if args.truth_port > 0 else ""
        print(f"\n[sim] open http://localhost:{args.http}/viewer{truth}   (Ctrl-C to stop)\n", flush=True)
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
