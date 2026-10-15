"""Encode and decode the messages in docs/MESSAGES.md.

Keep this boring. A message is a dict with a "t" (type) and a "ts" (sender time).
`encode` adds "ts" if missing and turns the dict into bytes. `decode` turns bytes
back into a dict and rejects anything that isn't a known type or is missing
required fields. Validation is deliberately light: enough to catch a typo on one
side, not a full schema.
"""

from __future__ import annotations

import json
import time

# type -> fields that must be present (besides "t" and "ts")
TYPES: dict[str, tuple[str, ...]] = {
    "cmd": ("seq", "throttle", "steer", "conveyor", "mode"),
    "hb": ("from",),
    "tlm": ("lat", "lon", "heading_deg", "batt_pct", "mode"),
    "trail": ("i", "lat", "lon", "signal_dbm"),
    "wps": ("id", "points"),
    "ack": ("for", "ok"),
    "evt": ("kind",),
}

MODES = ("DRIVEN", "AUTO", "COMING_HOME")


class BadMessage(ValueError):
    pass


def encode(t: str, body: dict | None = None) -> bytes:
    if t not in TYPES:
        raise BadMessage(f"unknown message type {t!r}")
    msg = {"t": t, "ts": time.time()}
    if body:
        msg.update(body)
    _check(msg)
    return json.dumps(msg, separators=(",", ":")).encode()


def decode(data: bytes) -> dict:
    try:
        msg = json.loads(data.decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise BadMessage(f"not json: {e}") from e
    if not isinstance(msg, dict):
        raise BadMessage("not an object")
    _check(msg)
    return msg


def _check(msg: dict) -> None:
    t = msg.get("t")
    if t not in TYPES:
        raise BadMessage(f"unknown message type {t!r}")
    if "ts" not in msg:
        raise BadMessage("missing ts")
    missing = [f for f in TYPES[t] if f not in msg]
    if missing:
        raise BadMessage(f"{t} missing {missing}")
    if t == "cmd":
        for f in ("throttle", "steer"):
            v = msg[f]
            if not isinstance(v, (int, float)) or not -1.0 <= v <= 1.0:
                raise BadMessage(f"cmd.{f} must be a number in [-1, 1], got {v!r}")
        if msg["mode"] not in MODES:
            raise BadMessage(f"cmd.mode must be one of {MODES}")
    if t == "wps" and not all(len(p) == 2 for p in msg["points"]):
        raise BadMessage("wps.points must be [lat, lon] pairs")
