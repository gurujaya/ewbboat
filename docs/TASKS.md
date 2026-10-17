# Master task list

Everything our team has to do, by phase. Each job folder has its own `TASKS.md` with the same items in more detail; this is the overview Project Management can pull into the schedule.

Tick a box in the same commit that finishes the work. Week 1 is the week of Oct 12, 2026. PM's schedule wins once it's out.

## Phase 1: plan and parts (weeks 1–2)

Gate: parts are ordered or found.

- [ ] Team agrees on `docs/ARCHITECTURE.md`
- [x] Everyone has a name on a job (see `docs/TEAM.md`)
- [x] `docs/MESSAGES.md` reviewed by the Pi, station, and dashboard owners
- [ ] Decide Arduino vs ESP32
- [ ] Decide which Wi-Fi bridge radios
- [ ] Decide ground station power (outlet or battery pack)
- [ ] Check what the club already has: Pis, Arduinos, cameras, gamepad, SD cards
- [ ] Price the rest and send the list to PM for the BOM
- [ ] Give Research our power draw (~12–15 W)
- [ ] Get from Electrical: motor controllers, sensor models, pin list, battery voltages
- [ ] Confirm with Mechanical: island size, mast, camera windows (Rev C)

## Phase 2: drive it on a table (weeks 3–4)

Gate: drive it from the dashboard while it sits on a table.

- [ ] Arduino: `M` line parsing, motor output, 2 s watchdog
- [ ] Arduino: `T` line with GPS, compass, battery (sensors can be `nan` for now)
- [ ] Pi: serial link to Arduino, both directions
- [ ] Pi: heartbeat send/receive, `cmd` receive, `tlm` send
- [ ] Pi: camera stream running
- [ ] Pi: log every `tlm` to CSV on the SD card
- [ ] Station: UDP listener, heartbeat, `cmd` forward
- [ ] Station: save `tlm` and `trail` to SQLite
- [ ] Station: web server up, serves the dashboard, re-serves video
- [ ] Station: own Wi-Fi network (hostapd) and a fixed address for the boat
- [ ] Dashboard: video panel, readings strip, battery, signal, mode
- [ ] Dashboard: gamepad → `cmd` at 10 Hz, Take control lock
- [ ] Dashboard: map with the boat marker (any map tiles; offline tiles later)
- [x] Comms: `boatlink` package done and tested on two laptops
- [ ] Comms: both bridges configured, boat and station on the same network
- [ ] Test: gamepad moves motors on the table through the whole chain

## Phase 3: safety rules, then water (weeks 5–7)

Gate: it comes back on its own when we cut the signal.

- [ ] Arduino: read the four water sensors, calibrate
- [ ] Arduino: battery averaging and the 10 % motor cut
- [ ] Pi: trail points every 3 m / 5 s with signal strength, send as `trail`
- [ ] Pi: lost-signal procedure (stop, wait, back to last good point, trail home)
- [ ] Pi: low-battery rules (warn, conveyor off + home, motors off)
- [ ] Pi: `COMING_HOME` mode, go-to-waypoint function (algorithm 1), Kp tuning
- [x] Pi + Arduino: GPS/compass at 5 Hz, GPS position filter, pure-pursuit path following, trail clean-up (tuned in the sim; pool tuning still to do)
- [x] Pi: driving fence (circle around the station) in `DRIVEN`
- [x] Pi: home = the averaged first fixes at the jetty (`tlm.home`); every trip home ends there
- [x] Pi: the path follower learns the current's push (crabs into a cross-current instead of sitting off its row)
- [x] Sim: `montecarlo.py`, hundreds of graded fast-time runs across currents, GPS noise and seeds
- [x] Sim: the simulator inside the browser (`sim/browser`) and the public link on GitHub Pages
- [x] Station: map squares and sweep rows sized to the scoop (0.8 m); "covered" = the belt went over it; every-other-row turn pattern
- [ ] Mechanical: confirm the scoop width (pontoon gap) and where the belt lip sits; `SCOOP_WIDTH_M` in ground-station/config.py and the funnel in sim/physics.py both depend on it
- [ ] Pi: fence check in every mode
- [ ] Station: `evt` feed stored and shown
- [ ] Dashboard: trail drawn live, Come home button, event feed, LINK LOST state
- [ ] Dashboard: export run as CSV
- [ ] Comms: range test over water, write the number into `ARCHITECTURE.md`
- [ ] Testing: all four sensors calibrated, numbers in `testing/calibration.md`
- [ ] Testing: a log file for every test run
- [ ] Test: unplug the Pi, motors stop within 2 s
- [ ] Test: unplug the station radio, boat follows the trail back
- [ ] Test: fake a low battery, warning shows, boat heads home
- [ ] Test: pool run, then lake run with a rope
- [ ] Test: 1 hour continuous run, still logging at the end

## Phase 4: autopilot and map (weeks 8–9, stretch)

Gate: it sweeps a rectangle on its own.

- [ ] Station: rectangle → waypoint list (lawnmower rows), send as `wps`
- [ ] Pi: `AUTO` mode, run algorithm 1 over the list, `wp_reached` and `sweep_done` events
- [ ] Station: 3 m grid, coverage marking, per-square averages
- [ ] Dashboard: draw the rectangle, Start sweep, coverage overlay, heat map layer, trash pin button
- [ ] Dashboard: coverage % and "sweep what's missed"
- [ ] Camera: trash detection on the front camera, nudge the next waypoint (only if everything above is done)
- [ ] Test: full sweep of a small rectangle in the pool, then on the lake

## Always

- [ ] Engineering notebook entry every time something works for the first time
- [ ] Diagrams and the message spec kept current for the final report
- [ ] Showcase demo plan (`testing/demo.md`): map on a screen, boat in the water
- [ ] `testing/parts.md` kept current for the BOM
