# comms

Owner: **Eric Cheguen Mendez** (`echeguen`). Branch: `comms`.

The boat and the ground station talk to each other over a radio. This job owns everything about that conversation: the code on both ends, the radios, the antenna, and the tests that tell us how far it reaches.

## The two deliverables

### 1. `boatlink/` — the Python package both sides import

The boat Pi and the station should not each write their own socket and heartbeat code. They both do:

```python
from boatlink import Link

link = Link(peer=("192.168.4.2", 5000), name="boat")   # or name="station"
link.on("cmd", handle_cmd)        # callback per message type from docs/MESSAGES.md
link.on_link_lost(handle_lost)    # fires after 3 s with no heartbeat from the peer
link.on_link_back(handle_back)
link.start()                      # background thread: receive, heartbeat 4x/s, watch the timer
link.send("tlm", {...})           # adds "t" and "ts", encodes JSON, sends one UDP packet
print(link.signal_dbm())          # read from the radio, or None if not available
```

What's inside:

```
comms/boatlink/
  __init__.py
  link.py        Link class: UDP socket, send(), receive thread, dispatch by "t"
  messages.py    encode/decode + validation for every type in docs/MESSAGES.md
  heartbeat.py   send "hb" 4x/s; link-lost after 3 s; link-back on the first hb after that
  signal.py      read signal strength (iw / the radio's web API), return dBm or None
  tests/         unit tests: encode/decode round trips, seq ordering, link-lost timing with a fake clock
```

Rules: standard library only (`socket`, `json`, `threading`, `time`). No external deps, so it installs anywhere. Every message type in `docs/MESSAGES.md` has an encoder, a decoder, and a test.

### 2. The radios, and how far they reach

```
comms/
  radios.md        which bridge pair we picked and why, settings, channel, fixed addresses
  antenna.md       mast height, cable, where it sits on the island (with Mechanical)
  range-test.md    step-by-step: how to run a range test
  logs/            one file per test: date, place, distance vs dBm, notes
  scripts/
    log_signal.py  log distance-from-station vs signal_dbm once a second (uses boatlink)
```

## Range test, short version

1. Station on its pole on shore, boat on the water (or carried along the shore for a first test).
2. Run `scripts/log_signal.py` on the station.
3. Move the boat out in a straight line, pausing every 25 m.
4. Note where signal drops below −80 dBm and where the link is lost.
5. Save the log in `logs/`. The distance goes into `docs/ARCHITECTURE.md` as the DRIVEN fence radius.

## Who you work with

- **Guru** for the station side (`ground-station/link.py` just wraps `boatlink`).
- **Zachary** for the boat side (`boat-pi/radio.py` just wraps `boatlink`) and the lost-signal test.
- **Mechanical** for the mast and antenna spot.
- **Research** for the test site, which decides the range we need.
