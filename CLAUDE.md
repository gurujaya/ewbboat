# CLAUDE.md

Instructions for Claude Code when working in this repo. Humans: this is also a decent one-page summary.

## What this is

Software for a student-built trash-collecting surface boat (Engineers Without Borders, Montgomery College, Fall 2026). Three parts: the boat, a ground station on shore, and a browser dashboard. The team is students with mixed experience, so prefer simple, readable code over clever code, and leave comments that explain *why*.

Read `docs/ARCHITECTURE.md` for the design and `docs/MESSAGES.md` for every message format before touching anything that sends or receives data.

## Layout

```
boat-arduino/    C++ (Arduino). Motors, conveyor, sensors, GPS, compass, battery, safety stop.
boat-pi/         Python 3. Radio link, camera, trail points, coming home, autopilot, SD logging.
ground-station/  Python 3. Link to boat, SQLite, FastAPI web server, map building.
dashboard/       Plain HTML + JS (no framework unless the team agrees). Video, map, readings, gamepad.
radio-testing/   Radio setup notes, range-test scripts and logs.
docs/            ARCHITECTURE, MESSAGES, TASKS, TESTING.
```

Each job folder has a `README.md` and a `TASKS.md`. When you finish a task, tick it in `TASKS.md` in the same commit.

## Rules

- **Branches.** One per job, same name as the folder. Never commit to `main`; changes reach `main` by pull request. See `CONTRIBUTING.md`.
- **Messages are shared.** Any field that crosses the radio or the USB cable is defined in `docs/MESSAGES.md`. Change the doc first, then the code on both sides. Don't add undocumented fields.
- **Safety first.** The Arduino must stop the motors if it hears nothing from the Pi for 2 seconds. The Pi must stop and run the lost-signal rules if it hears no heartbeat from the station for 3 seconds. Never remove or weaken these to make a test pass.
- **Units.** Meters, seconds, degrees (0–360, clockwise from north), volts, dBm. Latitude/longitude as decimal degrees. Say the unit in variable names when it isn't obvious (`dist_m`, `heading_deg`).
- **Motor commands** are two floats, `left` and `right`, each in [-1, +1]. The Arduino scales them to the driver. Nothing else sends motor commands directly; the autopilot goes through the same path as the gamepad.
- **Modes.** The boat is always in exactly one of `DRIVEN`, `AUTO`, `COMING_HOME`. Safety transitions happen on the Pi, never on the dashboard.
- **No secrets in the repo.** Wi-Fi passwords, keys, and anything local go in `.env` or `*.local.json` (gitignored).
- **Python style.** Standard library first. Dependencies go in that folder's `requirements.txt` with a comment saying why. Type hints on function signatures. `black` formatting.
- **Arduino style.** One `.ino` plus small `.h/.cpp` files per concern (motors, sensors, serial). No blocking `delay()` in the main loop; use `millis()` timing.
- **Tests.** Pure logic (bearing math, trail search, mixing formula, battery thresholds) gets a unit test in `tests/` inside that folder. Hardware-dependent code gets a manual test procedure written in `docs/TESTING.md`.

## When asked to implement something

1. Find it in that folder's `TASKS.md` and `docs/TASKS.md`. If it isn't there, add it first.
2. Check `docs/MESSAGES.md` for any fields involved.
3. Write the code, the test, and a line in the folder `README.md` if setup changed.
4. Tick the task. Commit with the `area: what changed` format.

## Hardware assumptions (update when the other teams decide)

- Two thrusters, differential steering, no rudder.
- One conveyor gearmotor, on/off only.
- Water sensors: temperature, pH, turbidity, conductivity. Exact modules TBD by Electrical.
- GPS module over UART, compass/IMU over I2C, on the Arduino.
- Raspberry Pi 4/5 on the boat and another at the station. Pi camera on the boat.
- Boat ↔ station: outdoor Wi-Fi bridge radios. Station ↔ laptop: the station's own Wi-Fi.
- Battery voltage read on an Arduino analog pin through a divider. Thresholds in `ARCHITECTURE.md` are placeholders until Electrical gives real voltages.
