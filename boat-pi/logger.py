"""Every telemetry message to a dated CSV on the SD card."""

from __future__ import annotations

import csv
import os
import time

# lat/lon are the filtered position (same as tlm); raw_lat/raw_lon are the GPS fix as it came
# from the Arduino, so a run can be checked afterwards for how much the filter smoothed.
FIELDS = [
    "ts", "lat", "lon", "raw_lat", "raw_lon", "heading_deg", "speed_mps", "gps_fix", "sats",
    "batt_v", "batt_pct", "signal_dbm", "mode", "home_phase", "left", "right", "conveyor",
    "temp_c", "ph", "turb_ntu", "cond_us", "trail_len", "wp_index", "target_lat", "target_lon",
]


class CsvLogger:
    def __init__(self, log_dir: str):
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, time.strftime("run-%Y%m%d-%H%M%S.csv"))
        self.f = open(path, "w", newline="")
        self.w = csv.DictWriter(self.f, fieldnames=FIELDS, extrasaction="ignore")
        self.w.writeheader()
        self.path = path

    def write(self, tlm: dict) -> None:
        row = dict(tlm)
        row.update(tlm.get("water") or {})
        self.w.writerow(row)
        self.f.flush()

    def close(self) -> None:
        self.f.close()
