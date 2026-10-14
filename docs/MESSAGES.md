# Message formats

Everything that crosses the radio or the USB cable is defined here. If you need a new field, change this file first in its own pull request, then change both sides.

All radio messages are JSON over UDP, one message per packet, UTF-8. Keep them small: a packet should stay well under 1 KB.

Units everywhere: meters, seconds, degrees (0–360 clockwise from north), volts, dBm, decimal-degree lat/lon. Timestamps are Unix seconds with decimals (`1760476327.42`).

Every message has a `t` (type) and a `ts` (sender's timestamp).

---

## Radio: laptop ↔ station ↔ boat

### 1. Command  (`"t": "cmd"`)

Laptop → station → boat. Sent ~10 times a second while someone holds control, and once whenever a button is pressed.

```json
{
  "t": "cmd",
  "ts": 1760476327.42,
  "seq": 1842,
  "throttle": 0.60,
  "steer": -0.15,
  "conveyor": true,
  "mode": "DRIVEN"
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `seq` | int | Counts up by 1 each command. The boat ignores a command whose `seq` is lower than the last one it saw (packets can arrive out of order). |
| `throttle` | float −1..+1 | forward is positive |
| `steer` | float −1..+1 | positive turns right |
| `conveyor` | bool | conveyor motor on/off |
| `mode` | `"DRIVEN"` / `"AUTO"` / `"COMING_HOME"` | what the operator is asking for. The boat may refuse (see Modes below). |

Optional, only when starting a sweep:

```json
  "sweep": { "corners": [[lat, lon], [lat, lon], [lat, lon], [lat, lon]], "row_spacing_m": 0.3 }
```

The station converts the rectangle into waypoints and sends them as a separate `wps` message (below); the boat never computes the sweep itself.

### 2. Heartbeat  (`"t": "hb"`)

Both directions, 4 times a second, always, even when nobody is driving. This is how each side knows the link is alive.

```json
{ "t": "hb", "ts": 1760476327.42, "from": "station" }
```

`from` is `"station"` or `"boat"`.

Rules:
- Boat hears no station heartbeat for **3 s** → lost-signal procedure starts (`ARCHITECTURE.md`, Level 2).
- Station hears no boat heartbeat for 3 s → dashboard shows "LINK LOST" and the boat marker goes grey.

### 3. Telemetry  (`"t": "tlm"`)

Boat → station, once a second. The station saves every one of these.

```json
{
  "t": "tlm",
  "ts": 1760476327.42,
  "lat": 39.09123,
  "lon": -77.15340,
  "heading_deg": 212.5,
  "speed_mps": 0.8,
  "gps_fix": true,
  "sats": 9,
  "batt_v": 12.1,
  "batt_pct": 78,
  "signal_dbm": -61,
  "mode": "DRIVEN",
  "left": 0.45,
  "right": 0.75,
  "conveyor": true,
  "water": { "temp_c": 21.4, "ph": 7.6, "turb_ntu": 12.0, "cond_us": 410 },
  "trail_len": 143,
  "wp_index": 7
}
```

| Field | Meaning |
| --- | --- |
| `gps_fix`, `sats` | whether the GPS has a fix and how many satellites. With no fix, `lat`/`lon` are the last known. |
| `batt_v`, `batt_pct` | voltage, averaged over 5 s, and the percentage the boat computed from it |
| `signal_dbm` | radio signal strength as the boat sees it |
| `mode` | the mode the boat is actually in (may differ from what was asked) |
| `left`, `right` | what the motors are currently being told, −1..+1 |
| `water.*` | the four readings. `null` for a sensor that isn't connected yet. |
| `trail_len` | how many trail points the boat has saved this run |
| `wp_index` | which waypoint it's heading for in `AUTO`, else `null` |

### 4. Trail point  (`"t": "trail"`)

Boat → station, whenever the boat saves a new trail point (every ~3 m or 5 s). Lets the dashboard draw the trail live and gives the station a copy.

```json
{ "t": "trail", "ts": 1760476327.42, "i": 143, "lat": 39.09123, "lon": -77.15340, "signal_dbm": -61 }
```

### 5. Waypoints  (`"t": "wps"`)

Station → boat, once, when a sweep starts. The boat replies with an `ack`.

```json
{ "t": "wps", "ts": 1760476327.42, "id": "sweep-7", "points": [[39.0912, -77.1534], [39.0913, -77.1521], ...] }
```

### 6. Ack  (`"t": "ack"`)

Boat → station, in reply to a `wps` or to a mode change the boat accepted or refused.

```json
{ "t": "ack", "ts": 1760476327.42, "for": "sweep-7", "ok": true, "msg": "" }
{ "t": "ack", "ts": 1760476327.42, "for": "mode", "ok": false, "msg": "battery below 20 %, staying in COMING_HOME" }
```

### 7. Event  (`"t": "evt"`)

Boat → station, when something notable happens. The station logs these and the dashboard shows them in a feed.

```json
{ "t": "evt", "ts": 1760476327.42, "kind": "link_lost", "detail": "no station heartbeat for 3.1 s" }
```

`kind` is one of: `link_lost`, `link_back`, `batt_warn`, `batt_low`, `batt_critical`, `fence_exit`, `mode_change`, `wp_reached`, `sweep_done`, `trash_seen`, `arduino_silent`.

### Video

Not JSON. The boat Pi runs a video stream (start with RTSP from the Pi camera; switch to WebRTC later if latency is bad). The station re-serves it to the dashboard. Video lives on its own port and never shares a packet with the messages above.

---

## USB serial: Pi ↔ Arduino

115200 baud, one line per message, newline-terminated, plain ASCII. Kept deliberately simpler than the radio messages: the Arduino has little memory and no JSON library by default.

### Pi → Arduino, 10 times a second

```
M <left> <right> <conveyor>\n
```

Example: `M 0.45 0.75 1`

`left` and `right` are floats −1..+1 with two decimals. `conveyor` is `0` or `1`.

Rule: **if the Arduino receives no valid `M` line for 2 s, it sets both motors to 0 and the conveyor to 0.** This never gets removed.

### Arduino → Pi, once a second

```
T <lat> <lon> <heading> <fix> <sats> <batt_v> <temp> <ph> <turb> <cond>\n
```

Example: `T 39.09123 -77.15340 212.5 1 9 12.10 21.4 7.6 12.0 410`

A missing sensor sends `nan` in its slot. The Pi parses this into the `tlm` message above.

### Arduino → Pi, when it happens

```
E <code>\n
```

`E STOP_NO_PI` when the 2-second watchdog fired. `E GPS_LOST` when the fix drops. `E BATT_LOW` when the averaged voltage crosses a threshold (the Arduino also enforces the 10 % motor cut itself, so it works even if the Pi is dead).

---

## Modes and who may change them

| From → To | Who | Condition |
| --- | --- | --- |
| any → `COMING_HOME` | boat (Pi) | link lost 3 s, battery ≤ 20 %, outside fence, or operator pressed Come home |
| `DRIVEN` → `AUTO` | operator | link up, battery > 30 %, a `wps` list received and acked |
| `AUTO` → `DRIVEN` | operator | link up |
| `COMING_HOME` → `DRIVEN` | operator | link up and battery > 20 % |
| `COMING_HOME` → `AUTO` | nobody | must go through `DRIVEN` first |

The boat is the authority. A `cmd` asking for a mode the rules don't allow gets an `ack` with `ok: false`.
