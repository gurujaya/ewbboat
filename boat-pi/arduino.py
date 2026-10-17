"""Serial link to the Arduino. The only file on the Pi that touches the hardware
that moves the boat. Line protocol is in docs/MESSAGES.md, "USB serial".

In the simulator the other end of the pty is the real firmware logic
(boat-arduino/boat/src) compiled for the laptop, driven by sim/fake_arduino.py.
Same lines, same code here.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass, field

import serial

log = logging.getLogger("arduino")


@dataclass
class ArduinoState:
    lat: float = 0.0
    lon: float = 0.0
    heading_deg: float = 0.0
    gps_fix: bool = False
    sats: int = 0
    batt_v: float = float("nan")
    water: dict = field(default_factory=lambda: {"temp_c": None, "ph": None, "turb_ntu": None, "cond_us": None})
    signal_dbm: float | None = None      # sim only: comes from an "S" line
    last_t_line: float = 0.0
    events: list[str] = field(default_factory=list)
    # every GPS fix since main.py last looked: (time received, lat, lon). T lines
    # come 5 times a second and the main loop runs 10, so normally there's 0 or 1
    # here, but a busy moment can deliver two at once and the filter wants both.
    fixes: list[tuple[float, float, float]] = field(default_factory=list)


def _f(s: str) -> float | None:
    try:
        v = float(s)
    except ValueError:
        return None
    return None if math.isnan(v) else v


class Arduino:
    def __init__(self, port: str, baud: int):
        self.ser = serial.Serial(port, baud, timeout=0.2)
        self.state = ArduinoState()
        self.lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True, name="arduino-read")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
        self.send_motors(0.0, 0.0, False)
        self.ser.close()

    def send_motors(self, left: float, right: float, conveyor: bool) -> None:
        left = max(-1.0, min(1.0, left))
        right = max(-1.0, min(1.0, right))
        line = f"M {left:.2f} {right:.2f} {1 if conveyor else 0}\n"
        try:
            self.ser.write(line.encode())
        except serial.SerialException as e:
            log.warning("serial write failed: %s", e)

    def take_fixes(self) -> list[tuple[float, float, float]]:
        """The GPS fixes received since the last call, oldest first."""
        with self.lock:
            fixes, self.state.fixes = self.state.fixes, []
        return fixes

    def _read_loop(self) -> None:
        while self._running:
            try:
                raw = self.ser.readline()
            except serial.SerialException as e:
                log.warning("serial read failed: %s", e)
                time.sleep(0.5)
                continue
            if not raw:
                continue
            line = raw.decode(errors="replace").strip()
            if not line:
                continue
            with self.lock:
                self._parse(line)

    def _parse(self, line: str) -> None:
        parts = line.split()
        st = self.state
        if parts[0] == "T" and len(parts) == 11:
            lat, lon, hdg = _f(parts[1]), _f(parts[2]), _f(parts[3])
            if lat is not None and lon is not None:
                st.lat, st.lon = lat, lon
            if hdg is not None:
                st.heading_deg = hdg % 360.0
            st.gps_fix = parts[4] == "1"
            st.sats = int(parts[5]) if parts[5].isdigit() else 0
            v = _f(parts[6])
            st.batt_v = v if v is not None else float("nan")
            st.water = {"temp_c": _f(parts[7]), "ph": _f(parts[8]), "turb_ntu": _f(parts[9]), "cond_us": _f(parts[10])}
            st.last_t_line = time.time()
            if st.gps_fix and lat is not None and lon is not None:
                st.fixes.append((st.last_t_line, lat, lon))
                del st.fixes[:-20]      # nobody reading (tests, startup)? don't grow forever
        elif parts[0] == "E" and len(parts) >= 2:
            st.events.append(parts[1])
        elif parts[0] == "S" and len(parts) == 2:
            st.signal_dbm = _f(parts[1])
        else:
            log.debug("ignored line: %r", line)
