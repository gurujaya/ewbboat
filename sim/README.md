# sim

The whole boat on one laptop, no hardware. The real `boat-pi` and `ground-station` code runs unchanged, and so does the Arduino firmware's logic (compiled for the laptop). Only the Arduino's pins and sensors, and the water, are fake.

```
                  pty (/tmp/boat-serial)            UDP 127.0.0.1               WebSocket
 fake_arduino.py  <--------------------->  boat-pi/main.py  <---------->  ground-station/main.py  <--------->  browser
 (physics.py)       M / T / E / S lines      (the real code)    cmd/hb/tlm      (the real code)           /viewer (three.js)
      |
      | stdin/stdout: rx / tick / tx / out
      v
 boat-host  = boat-arduino/boat/src (the real firmware logic) built for the laptop
```

## Run it

```bash
pip install -r boat-pi/requirements.txt -r ground-station/requirements.txt
python sim/run.py          # first run compiles the Arduino firmware for your laptop (a few seconds)
# open http://localhost:8000/viewer
```

In the viewer: **Drive** (takes control and asks the boat for DRIVEN), then W A S D or a gamepad, C for the conveyor; on a phone or tablet, drag the on-screen stick (let go to stop) and tap Conveyor. **Sweep**, then click two corners on the water. **Home**. Watch the trail change color as the signal weakens, and drive past the radio range to see the boat stop, wait, back up, and come home on its own. Keys 1 / 2 / 3 switch the camera between follow, free and a top-down map.

The same page also runs with no station at all: on a static host (the public link on GitHub Pages) or with `?local=1`, the whole simulator runs inside the page under Pyodide (`sim/browser/core.py`: the real `Boat` and `Station` classes with in-memory radio and Arduino stand-ins). See `sim/DEPLOY.md`.

The viewer only shows what the station knows. The boat sends its position 5 times a second (already smoothed by the boat's GPS filter), so between messages the model is moved along its reported heading at its reported `speed_mps` and eased toward each new one. Every effect comes from a real field: prop wash from `left`/`right`, the moving belt and drips from `conveyor`, the wake from speed, the radio pulses from `signal_dbm`, the grey boat and red banner from the station's link state.

Knobs:

```bash
python sim/run.py --range 120          # radio dies at 120 m (default 200)
python sim/run.py --current 0.4,0.1    # strong current pushing east
python sim/run.py --noise 3            # worse GPS
python sim/run.py --drain 20           # battery dies in minutes; watch 30/20/10 % fire
ROW_SPACING_M=3 python sim/run.py      # quick-demo sweep rows (default 0.65 m = scoop width x 0.8: full coverage, ~5x longer)
python sim/run.py --start 0,80         # launch 80 m out (default: alongside the jetty, 4.5 m east, 9.5 m north)
                                       # the boat stays tied up there, drifting nowhere, until the first motor command
```

Running a second sim at the same time? Give it its own ports and serial link:
`STATION_PORT=5100 BOAT_PORT=5101 SIM_SERIAL_LINK=/tmp/boat-serial-2 python sim/run.py --http 8001 --db /tmp/sim2.sqlite --truth-port 8098`

## Trash

The lake starts with 30 pieces of floating litter (bottles, bags, cups, cans) scattered 12–70 m north of the station and up to 45 m either side, at least 3 m apart and never right at the jetty. Placement is seeded, so the same lake comes back every run. `--trash 0` gives a clean lake, `--trash 100` a dirty one.

The pieces drift at ~90 % of the current (a floating object lags the water a little) plus a tiny random wander, and nothing drifts south of the beach at y = 2 m.

**Collecting.** The Rev C boat is a catamaran: the water between the two pontoons is funnelled onto the conveyor belt at the bow. So in the sim a piece is collected only when, in the boat's own frame, it is within **±0.4 m of the centerline** (the gap between the pontoons is about 0.8 m) and **0.2–0.9 m ahead of the boat's center**, **and** the conveyor is on (the firmware's `M` line, so the belt the operator asked for), **and** the boat is moving forward through the water (> 0.1 m/s). A stopped belt or a stopped boat just pushes litter around. The check uses TRUE positions, not GPS, because that's what happens on the water. Collected pieces are in the basket: they stop drifting and are counted. Constants are at the top of `BoatPhysics` in `physics.py`.

**Ground truth, sim only.** `fake_arduino.py` serves the TRUE state of the lake as JSON at `http://localhost:8099/truth` (`--truth-port`, env `SIM_TRUTH_PORT`, 0 = off). The real boat can't know any of this (it has no trash sensor), so nothing in `boat-pi` or `ground-station` reads it and nothing should. The viewer uses it only to draw the litter and show a collected count:

```json
{"t": 123.4, "total": 30, "collected": 2,
 "trash": [{"id": 1, "lat": 39.091515, "lon": -77.153180, "kind": "bottle", "collected": false, "collected_t": null}, ...],
 "boat": {"lat": 39.091285, "lon": -77.153348, "heading_deg": 12.3, "moored": false}}
```

`boat` is the TRUE position and heading (not the GPS, not the compass); comparing it with the telemetry shows how much the sensors lie.

## Prove it works without a browser

```bash
pip install websockets
python sim/headless_test.py
```

Drives north, sweeps a 30 × 20 m rectangle, comes straight home, drives out of radio range, and checks the boat backs up along its trail until the link returns. At the end it prints accuracy numbers: how far the boat strayed from the planned sweep rows (cross-track RMS and max) and how long the trip home took, with pass limits explained at the top of the file. Takes about 10 minutes. Run it before opening a pull request that touches `boat-pi`, `ground-station`, or `comms`.

## Hundreds of lake trips in a second

```bash
python sim/montecarlo.py            # 120 runs: 5 currents x 3 GPS noise levels x 4 seeds, two scenarios
python sim/montecarlo.py --quick    # 8 runs
python sim/montecarlo.py --runs 10 --csv runs.csv
```

The same boat-pi code (GPS filter, path follower, trail, coming-home plan) stepped through `physics.py` with no clock, no pty and no radio: a 10-minute trip takes well under a second, and the runs go on all your CPU cores. Because the physics knows the boat's TRUE position, it measures what the lake can't tell you: how far the boat really was from its planned row, not just what its GPS thought. Two scenarios: a sweep and the straight trip home, and a lost link (drive out of range, wait, back up along the trail to good signal). Every run is graded; the limits and the reasoning are at the top of the file. Exit code 0 only if every run passes, so it's a quick gate before the 10-minute headless test.

It found three things on its first runs: pure pursuit alone sat a steady 1 m off its row in a 0.3 m/s cross-current (the follower now learns the push and crabs into it); the follower called "arrived" when it passed the end point 3 m wide (it now turns back); and the nose wagged ~11 deg/s on straight rows because the steering gain was too hot for a hull with 0.4 s of yaw lag (gain lowered; see the note above `KP` in `boat-pi/config.py`, including what made it worse). Tuning knobs: `--set KP=0.01` overrides any `boat-pi/config.py` value, `--phys YAW_LAG=0.8` any `BoatPhysics` constant, `--noises 0.5,3` the GPS noise levels. What it can't tell you: anything about the serial line, the radio, the station, or timing; that's what `headless_test.py` is for.

## What's fake and what's real

| Piece | In the sim | On the boat |
| --- | --- | --- |
| Arduino logic: `M` parsing, 2 s watchdog, battery warnings and 10 % cut, `T`/`E` lines | **the real firmware code** (`boat-arduino/boat/src/`), compiled for the laptop as `boat-arduino/build/boat-host` | the same code compiled for the board |
| Arduino pins and sensors (the HAL) | `fake_arduino.py` gives the firmware readings from `physics.py` and moves the boat with its motor outputs | `boat.ino`: real pins, GPS, compass, ADC |
| Serial cable | a pty at `/tmp/boat-serial`, plus a sim-only `S <dbm>` line from `fake_arduino.py` | USB on `/dev/ttyUSB0` |
| Water, current, GPS noise, battery drain | `physics.py` | the lake |
| Trash | `physics.py`: seeded floating pieces that drift with the current; collected when they pass between the pontoons with the belt on. True positions served sim-only at `/truth` for the viewer to draw | real litter; the boat has no trash sensor, so "collected" is whatever is in the basket when it comes back |
| Radio | `boatlink` over localhost; packets dropped when the fake signal is below −88 dBm | `boatlink` over the Wi-Fi bridges |
| Signal strength | from the `S` line | `iw dev wlan0 link` |
| Everything else | real code | real code |

Switching to hardware is `BOAT_ENV=boat` plus the addresses in `boat-pi/config.py` and `ground-station/config.py`.

A C++ compiler is needed for the firmware build (macOS: `xcode-select --install`; Ubuntu/Debian: `sudo apt install g++`). `run.py` tells you if it can't find one.

## Files

```
sim/
  physics.py        the boat: prop thrust vs water drag, turning lag, a 4 % weaker right thruster, a current that
                    gusts, slowly-drifting GPS error (5 Hz), a compass 3 degrees off, battery drain; floating trash
                    that drifts and is collected between the pontoons
  fake_arduino.py   owns the pty, runs the real firmware (boat-host), feeds it physics readings, applies its motor
                    outputs; serves the sim-only ground truth (/truth) for the viewer
  tests/            pytest for physics.py: trash spawn, drift, the funnel rule, speed build-up and coasting
  run.py            builds boat-host if needed, then starts all three processes with the right environment
  headless_test.py  end-to-end check, no browser (10 min)
  montecarlo.py     hundreds of fast-time runs of the boat's math, graded (1 s)
  browser/core.py   the simulator in one process with no network, for running inside a web page
  browser/build_site.py  assembles the static site (viewer + the Python it needs)
  viewer/            station view of the lake. Reads the station's /ws, so it also shows the real boat.
    index.html       layout (Tailwind)
    js/main.js       websocket, smoothing between fixes, camera, driving, sweep picking, particle emitters
    js/world.js      sky, station, fences, trail, sweep plan, coverage grid, trash buoys
    js/surface.js    water + shore shader; the same waves the boat bobs on
    js/boat.js       the Rev C boat at real size
    js/particles.js  GPU particles: foam, spray, ripples
    js/ui.js         panels, event log, toasts (Motion)
    js/minimap.js    the north-up chart
    js/flotsam.js    SIM ONLY: floating trash from the ground-truth feed, and the scooped count
    vendor/          three.js, Tailwind, Motion, fonts: no internet needed at the lake
```

## Things the sim found already

- A sweep rectangle used as the fence before the boat had reached it kicked the boat out of AUTO on the first tick. Now the fence only applies after the first waypoint.
- A boat can orbit a waypoint it keeps missing by a meter. "Arrived" now also counts when the point is close and behind the boat.
- The boat's `link_lost` event is sent over the link that just died, so it never arrived. Events are now held and delivered when the link returns.
- At the edge of range the link flickered on and off every second. The boat now needs 4 dB of margin before it calls the link good again.

- The boat zig-zagged along sweep rows and crawled home. It was steering 10 times a second on GPS and compass readings that only arrived once a second, on raw GPS jitter, and it slowed down to "arrive" at every trail point (one every 3 m). Now the Arduino sends GPS + compass 5 times a second, the Pi smooths the GPS (`PositionFilter`), and the autopilot follows the line instead of hopping between points (pure pursuit, `autopilot.PathFollower`).

None of those would have been fun to discover on the lake.
