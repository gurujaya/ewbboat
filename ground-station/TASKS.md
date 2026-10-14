# ground-station tasks

## Phase 1
- [ ] Station Pi set up: OS, SSH, static IP on the boat link
- [ ] Review `docs/MESSAGES.md` with the boat-pi owner; agree on ports and the boat's address
- [ ] Decide station power with the team (outlet vs battery pack)

## Phase 2: table
- [ ] `link.py`: UDP receive, heartbeat 4×/s, link-lost after 3 s
- [ ] `db.py`: schema for tlm, trail, evt, ack, runs, sweeps; insert on every message
- [ ] `api.py`: FastAPI app serving `../dashboard/` and a `/ws` that pushes every message live
- [ ] `control.py`: take-control lock, dashboard input → `cmd` at 10 Hz with `seq`
- [ ] `video.py`: re-serve the boat's RTSP stream to the browser
- [ ] `setup/`: hostapd + dnsmasq so the station makes its own Wi-Fi; systemd unit for boot
- [ ] `--fake-boat` mode that replays a CSV so dashboard work doesn't need hardware
- [ ] Test: dashboard on a phone sees live readings from the boat on the table

## Phase 3: coming home
- [ ] Store `trail` and `evt`; `/ws` pushes them; `/api/history` returns a run
- [ ] `/api/export.csv` for a run (every tlm row with time and lat/lon)
- [ ] Show the boat's answer to a mode request (`ack`) on the dashboard feed
- [ ] Range test support: log `signal_dbm` vs distance from the station; write the number in ARCHITECTURE
- [ ] Test: 1 hour run; row counts match the boat's CSV

## Phase 4: autopilot and map
- [ ] `sweep.py`: rectangle → lawnmower waypoints, row spacing from config, numbered; unit test
- [ ] `/api/sweep`: accept corners, build the list, send `wps`, wait for `ack`
- [ ] `grid.py`: 3 m squares, mark covered on each trail point, per-square averages of the four readings; unit test
- [ ] `/api/grid` for the dashboard overlay and heat map; coverage %
- [ ] "Sweep what's missed": uncovered squares → new rectangle(s)
- [ ] Test: full small sweep end to end

## Always
- [ ] Schema changes go in `db.py` with a comment and in README
