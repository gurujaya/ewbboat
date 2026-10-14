# boat-pi tasks

## Phase 1
- [ ] Pi set up: OS, SSH, Python venv, camera works with `libcamera-hello`
- [ ] Review `docs/MESSAGES.md` with the station owner; agree on ports
- [ ] `config.py` with every threshold from ARCHITECTURE as a named constant

## Phase 2: table
- [ ] `arduino.py`: open serial, send `M` at 10 Hz, parse `T` and `E`
- [ ] `radio.py`: UDP socket, send/receive JSON, heartbeat 4×/s
- [ ] Receive `cmd`, apply the mixing formula, send to Arduino
- [ ] Ignore `cmd` with an older `seq`
- [ ] Build and send `tlm` once a second
- [ ] `camera.py`: RTSP stream from the Pi camera
- [ ] `logger.py`: every `tlm` to a dated CSV on the SD card
- [ ] Unit tests: mixing formula, seq handling
- [ ] Test: gamepad on the laptop moves the motors on the table

## Phase 3: coming home
- [ ] `trail.py`: save a point every 3 m or 5 s with `signal_dbm`; send `trail`
- [ ] `trail.py`: `last_good_point(threshold_dbm)` and `path_home()`
- [ ] `nav.py`: `distance_m`, `bearing_deg`, `wrap_deg`, `go_to_waypoint()` with Kp
- [ ] `modes.py`: state machine with the allowed transitions from MESSAGES.md
- [ ] `safety.py`: lost-signal procedure exactly as ARCHITECTURE Level 2
- [ ] `safety.py`: battery rules at 30/20/10 %
- [ ] `safety.py`: fence check every loop, in every mode
- [ ] `COMING_HOME`: drive the trail backwards with `go_to_waypoint()`
- [ ] Send `evt` for every kind listed in MESSAGES.md
- [ ] Send `ack` for mode requests, refusing when the rules say no
- [ ] Unit tests: bearing/wrap edge cases (crossing 0/360), last_good_point, every mode transition
- [ ] Test: pull the station radio; boat stops, waits, backs up, goes home
- [ ] Test: fake battery 20 %; conveyor off, boat heads home
- [ ] Tune Kp in the pool; write the final value in config and README

## Phase 4: autopilot
- [ ] Receive `wps`, store the list, `ack` it
- [ ] `AUTO` mode: run the list, `wp_reached` per point, `sweep_done` at the end, then `COMING_HOME`
- [ ] Refuse `AUTO` when battery ≤ 30 % or no fix
- [ ] Stretch: `camera.py` detection loop, `trash_seen` event, nudge next waypoint 2 m
- [ ] Test: small sweep in the pool, then on the lake

## Always
- [ ] Setup steps that changed go in README the same day
