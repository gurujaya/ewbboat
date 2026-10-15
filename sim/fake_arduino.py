"""Pretends to be the Arduino, on the other end of a pseudo-terminal.

Speaks exactly the lines in docs/MESSAGES.md ("USB serial"), plus one sim-only
line, `S <dbm>`, so the boat Pi knows what the radio would be seeing.

    python fake_arduino.py --link /tmp/boat-serial [--current 0.2,0.1] [--range 200] [--noise 1.5]

It creates a symlink at --link pointing at the pty, so boat-pi can open a
stable path. 20 Hz physics, 1 Hz T lines, 2 s watchdog like the real thing.
"""

from __future__ import annotations

import argparse
import os
import pty
import select
import signal
import sys
import time

from physics import BoatPhysics, World

WATCHDOG_S = 2.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--link", default="/tmp/boat-serial")
    ap.add_argument("--current", default="0.15,0.05", help="east,north m/s")
    ap.add_argument("--range", type=float, default=200.0, help="radio range, m")
    ap.add_argument("--noise", type=float, default=1.5, help="gps noise, m")
    ap.add_argument("--start", default="0,15", help="start x,y m from station")
    ap.add_argument("--batt", type=float, default=12.6, help="starting volts")
    ap.add_argument("--drain", type=float, default=1.0, help="battery drain multiplier")
    args = ap.parse_args()

    cx, cy = (float(v) for v in args.current.split(","))
    sx, sy = (float(v) for v in args.start.split(","))
    world = World(current_mps=(cx, cy), gps_noise_m=args.noise, radio_range_m=args.range, start_xy=(sx, sy))
    boat = BoatPhysics(world)
    boat.batt_v = args.batt
    boat.DRAIN_V_PER_S_FULL *= args.drain
    boat.DRAIN_V_PER_S_IDLE *= args.drain

    master, slave = pty.openpty()
    slave_path = os.ttyname(slave)
    try:
        os.unlink(args.link)
    except FileNotFoundError:
        pass
    os.symlink(slave_path, args.link)
    print(f"fake arduino on {slave_path} (-> {args.link})", flush=True)

    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)

    last_m = 0.0
    last_t = 0.0
    last_step = time.time()
    buf = b""
    stopped_by_watchdog = False
    try:
        while running:
            r, _, _ = select.select([master], [], [], 0.05)
            now = time.time()
            if r:
                try:
                    buf += os.read(master, 4096)
                except OSError:
                    break
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    parts = line.decode(errors="replace").split()
                    if len(parts) == 4 and parts[0] == "M":
                        try:
                            boat.set_motors(float(parts[1]), float(parts[2]), parts[3] == "1")
                            last_m = now
                            stopped_by_watchdog = False
                        except ValueError:
                            pass
            # watchdog
            if now - last_m > WATCHDOG_S and (boat.left or boat.right or boat.conveyor):
                boat.set_motors(0.0, 0.0, False)
                if not stopped_by_watchdog:
                    os.write(master, b"E STOP_NO_PI\n")
                    stopped_by_watchdog = True
            # physics
            boat.step(now - last_step)
            last_step = now
            # T line once a second
            if now - last_t >= 1.0:
                last_t = now
                lat, lon = boat.gps()
                temp, ph, turb, cond = boat.water()
                t_line = f"T {lat:.6f} {lon:.6f} {boat.compass_deg():.1f} 1 9 {boat.batt_v:.2f} {temp:.1f} {ph:.2f} {turb:.1f} {cond:.0f}\n"
                s_line = f"S {boat.signal_dbm():.1f}\n"
                try:
                    os.write(master, t_line.encode() + s_line.encode())
                except OSError:
                    break
    finally:
        try:
            os.unlink(args.link)
        except FileNotFoundError:
            pass
        os.close(master)
        os.close(slave)


if __name__ == "__main__":
    main()
