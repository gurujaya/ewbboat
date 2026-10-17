# boat-pi tasks

Develop against `sim/run.py` until the hardware arrives; `python sim/headless_test.py` before every pull request.

## Phase 1
- [ ] Pi set up: OS, SSH, Python venv, camera works with `libcamera-hello`
- [ ] Review `docs/MESSAGES.md` with the station owner; agree on ports
- [x] `config.py` with every threshold from ARCHITECTURE as a named constant

## Phase 2: table
- [x] `arduino.py`: open serial, send `M` at 10 Hz, parse `T` and `E`
- [x] `radio.py`: wrap `comms/boatlink` (Eric's package); register callbacks for `cmd`, `wps`, link lost/back
- [x] Receive `cmd`, apply the mixing formula, send to Arduino
- [x] Ignore `cmd` with an older `seq`
- [x] Build and send `tlm` once a second
- [x] `tlm` at 5 Hz (matches the Arduino's 5 Hz `T` lines)
- [ ] `camera.py`: RTSP stream from the Pi camera
- [x] `logger.py`: every `tlm` to a dated CSV on the SD card
- [x] Unit tests: mixing formula, seq handling
- [ ] Test: gamepad on the laptop moves the motors on the table

## Phase 3: coming home
- [x] `trail.py`: save a point every 3 m or 5 s with `signal_dbm`; send `trail`
- [x] `trail.py`: `last_good_point(threshold_dbm)` and `path_home()`
- [x] `nav.py`: `distance_m`, `bearing_deg`, `wrap_deg`, `go_to_waypoint()` with Kp
- [x] `modes.py`: state machine with the allowed transitions from MESSAGES.md
- [x] `safety.py`: lost-signal procedure exactly as ARCHITECTURE Level 2
- [x] `safety.py`: battery rules at 30/20/10 %
- [x] `safety.py`: fence check every loop, in every mode
- [x] `COMING_HOME`: drive the trail backwards with `go_to_waypoint()`
- [x] Send `evt` for every kind listed in MESSAGES.md
- [x] Send `ack` for mode requests, refusing when the rules say no
- [x] Unit tests: bearing/wrap edge cases (crossing 0/360), last_good_point, every mode transition
- [ ] Test: pull the station radio; boat stops, waits, backs up, goes home
- [ ] Test: fake battery 20 %; conveyor off, boat heads home
- [x] `nav.py`: `PositionFilter` (alpha-beta) on every GPS fix; autopilot, fences, trail and `tlm` use the filtered position; `speed_mps` from it; raw + filtered in the CSV; unit tests
- [x] `nav.py` + `autopilot.py`: pure pursuit along a path (`PathFollower`) replaces stop-at-every-waypoint; used for the sweep, going home, backing up and the fence return; unit tests
- [x] `nav.simplify`: Douglas-Peucker + drop bunched points before following the trail home (raw trail kept)
- [x] `tlm.target`: the point the autopilot is steering at
- [x] Driving fence: circle of `DRIVEN_FENCE_M` around the station in `DRIVEN` → `fence_exit`, `FENCE` phase to 5 m inside, back to `DRIVEN`; unit tests for the geometry
- [x] Tune `LOOKAHEAD_M`, `KP`, `KD` and the filter gains in the sim (`sim/headless_test.py` prints the numbers)
- [ ] Tune `LOOKAHEAD_M`, `KP`, `KD` in the pool; write the final values in config and README
- [ ] Real row spacing (0.3 m) is far tighter than the boat can U-turn: decide how the sweep turns (e.g. skip rows and come back) before the lake sweep

## Phase 4: autopilot
- [x] Receive `wps`, store the list, `ack` it
- [x] `AUTO` mode: run the list, `wp_reached` per point, `sweep_done` at the end, then `COMING_HOME`
- [x] Refuse `AUTO` when battery ≤ 30 % or no fix
- [ ] Stretch: `camera.py` detection loop, `trash_seen` event, nudge next waypoint 2 m
- [ ] Test: small sweep in the pool, then on the lake

## Always
- [ ] Setup steps that changed go in README the same day
