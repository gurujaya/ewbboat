# ground-station

The Python on the shore Pi. Always on. Keeps the link to the boat, saves everything, builds the map, and serves the dashboard.

Branch: `ground-station`. Language: Python 3.11+, FastAPI, SQLite.

## What it owns

- UDP link to the boat: heartbeat, forward `cmd`, receive `tlm`/`trail`/`evt`/`ack`
- SQLite database: one table per message type, plus runs and waypoint lists
- Web server: serves `../dashboard/` as static files, a WebSocket for live data, REST for history and export
- Video: re-serves the boat's stream to browsers
- Sweep planning: rectangle → waypoint list → `wps` to the boat
- The map: 3 m grid, coverage, per-square averages
- Its own Wi-Fi network (hostapd + dnsmasq) for laptops and phones

Message formats: [`../docs/MESSAGES.md`](../docs/MESSAGES.md).

## Layout (to create)

```
ground-station/
  main.py            starts the UDP listener, the web server, the heartbeat
  config.py          ports, boat address, grid size, DB path
  link.py            UDP to the boat; heartbeat 4×/s; "boat link lost" after 3 s
  db.py              SQLite schema and inserts; one row per message
  api.py             FastAPI: /ws live feed, /api/history, /api/export.csv, /api/sweep
  control.py         who holds control; turns dashboard input into cmd at 10 Hz
  sweep.py           rectangle → lawnmower waypoints (row spacing from config)
  grid.py            3 m squares, coverage, averages, heat map data
  video.py           proxy the boat's stream
  setup/             hostapd.conf, dnsmasq.conf, systemd unit so it starts on boot
  tests/             sweep.py and grid.py get unit tests
  requirements.txt
```

## Setup

```bash
sudo apt install python3-venv hostapd dnsmasq
cd ground-station
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py
# open http://<station-ip>:8000 from a laptop on the station's Wi-Fi
```

`setup/README.md` (to write) covers making the Pi an access point and starting on boot.

## Rules

- Save first, then forward. Every message from the boat hits the DB before anything else looks at it.
- The station never decides a mode. It passes the operator's request along and shows what the boat answered.
- Only one `cmd` sender at a time (`control.py`). A second "take control" replaces the first and tells the dashboard.
- Keep the station runnable with the boat offline, so the dashboard can be developed without hardware. A `--fake-boat` flag that replays a CSV is worth building early.
