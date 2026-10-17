---
title: EWB Trash Boat Simulator
emoji: 🚤
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 8080
pinned: false
short_description: Drive, sweep and bring home a trash-collecting boat (sim)
---

# Boat software

Code and docs for the Software, Communications and Data team on the EWB-MC trash-collecting boat (Fall 2026).

This repo holds everything that runs on the boat, on the ground station on shore, and in the browser dashboard. It also holds the message formats the pieces use to talk to each other, so the boat side and the shore side never drift apart.

## The system in one picture

```
 laptop / phone  <--- station's Wi-Fi --->  ground station  <--- long-range Wi-Fi --->  the boat
 (any browser)                              (Pi on shore,                                Arduino: motors, sensors, failsafe
                                             always on,                                  Pi: radio, camera, trail, autopilot
                                             saves everything)
```

- The boat only ever talks to the ground station.
- The laptop only ever talks to the ground station.
- Close the laptop and nothing breaks. The station keeps saving, the boat keeps going.

Full write-up: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Folders = jobs

| Folder | What lives here | Language | Branch | Owner |
| --- | --- | --- | --- | --- |
| `boat-arduino/` | Motors, conveyor, sensors, GPS, compass, battery, the safety stop | C++ (Arduino) | `boat-arduino` | Guru |
| `boat-pi/` | Camera, trail points, modes, coming home, autopilot, SD logging | Python | `boat-pi` | Zachary |
| `ground-station/` | Database, web server, sweep planner, map building | Python | `ground-station` | Guru |
| `dashboard/` | The web page: video, map, readings, gamepad driving | HTML + JS | `dashboard` | Sebastian |
| `comms/` | Boat ↔ station link: the `boatlink` library, radios, antenna, range tests | Python + notes | `comms` | Eric |
| `testing/` | Parts and BOM, sensor calibration, test logs, charts, showcase demo | markdown + sheets | `testing` | Nicholas, Mir |
| `sim/` | Fake Arduino + lake physics + a three.js viewer; runs the real code with no hardware | Python + JS | any | Guru |
| `docs/` | Architecture, message formats, team, tasks, testing | markdown | `main` | everyone |

Who's who and what each person does: [docs/TEAM.md](docs/TEAM.md)

Every job folder has a `README.md` (what it is and how it fits) and a `TASKS.md` (the checklist for that job). Start there.

## Run it with no hardware

```bash
pip install -r boat-pi/requirements.txt -r ground-station/requirements.txt
python sim/run.py
# open http://localhost:8000/viewer
```

The real boat and station code against a fake Arduino and a fake lake. Drive it, sweep a rectangle, drive out of radio range and watch it come home. See [sim/README.md](sim/README.md).

## Getting started

```bash
git clone https://github.com/gurujaya/ewbboat.git
cd ewbboat
git checkout boat-pi        # your branch, from the table above
cat boat-pi/README.md
cat boat-pi/TASKS.md
```

How we branch, commit, and merge: [CONTRIBUTING.md](CONTRIBUTING.md)

## The four levels

1. **Remote control.** A person drives from the dashboard, video and readings come back. Meets every requirement on its own.
2. **Comes home.** Trail points, lost-signal rules, low-battery rules. The boat saves itself.
3. **Drives itself.** Waypoints, a sweep pattern, a fence, and a coverage map.
4. **Sees trash.** A camera spots trash and nudges the boat. Stretch goal.

Each level has to work before the next one starts. If we run out of time at level 2, we still have a working boat.

## Docs

- [docs/TEAM.md](docs/TEAM.md) — who owns which branch and what they do
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — how the whole thing works, from basic to advanced
- [docs/MESSAGES.md](docs/MESSAGES.md) — the four message types, field by field. Read this before writing any code that sends or receives anything.
- [docs/TASKS.md](docs/TASKS.md) — the master checklist across all jobs, by phase
- [docs/TESTING.md](docs/TESTING.md) — the tests each phase has to pass before we move on
