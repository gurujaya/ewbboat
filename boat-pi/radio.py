"""Thin wrapper around comms/boatlink. No socket code here."""

from __future__ import annotations

import os
import subprocess
import sys

# make comms/boatlink importable without installing it
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "comms"))

from boatlink import Link  # noqa: E402

import config


def make_link(signal_fn) -> Link:
    """signal_fn() -> current dBm or None. In the sim, packets drop below SIGNAL_DROP_DBM."""

    state = {"dropped": False}

    def out_of_range() -> bool:
        # hysteresis: drop below SIGNAL_DROP_DBM, come back only 4 dB above it,
        # so a boat sitting right at the edge doesn't flicker on and off every second
        s = signal_fn()
        if s is None:
            return False
        if state["dropped"]:
            if s > config.SIGNAL_DROP_DBM + 4:
                state["dropped"] = False
        elif s < config.SIGNAL_DROP_DBM:
            state["dropped"] = True
        return state["dropped"]

    return Link(
        name="boat",
        listen=config.BOAT_LISTEN,
        peer=config.STATION_ADDR,
        drop_when=out_of_range if config.ENV == "sim" else None,
    )


def read_wifi_dbm(iface: str = "wlan0") -> float | None:
    """Real hardware: ask the Wi-Fi driver. Returns None if it can't."""
    try:
        out = subprocess.run(["iw", "dev", iface, "link"], capture_output=True, text=True, timeout=1).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in out.splitlines():
        if "signal:" in line:
            try:
                return float(line.split("signal:")[1].split()[0])
            except (IndexError, ValueError):
                return None
    return None
