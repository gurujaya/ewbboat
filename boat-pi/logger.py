"""Every telemetry message to a dated CSV on the SD card."""

from __future__ import annotations

import csv
import os
import time

FIELDS = ["ts", "lat", "lon", "heading_deg", "gps_fix", "sats", "batt_v", "batt_pct", "signal_dbm", "mode", "left", "right", "conveyor", "temp_c", "ph", "turb_ntu", "cond_us", "trail_len", "wp_index"]


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
