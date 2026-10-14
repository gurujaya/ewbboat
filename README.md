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

| Folder | What lives here | Language | Branch |
| --- | --- | --- | --- |
| `boat-arduino/` | Motors, conveyor, sensors, GPS, compass, battery, the safety stop | C++ (Arduino) | `boat-arduino` |
| `boat-pi/` | Radio link, camera stream, trail points, coming home, autopilot, SD logging | Python | `boat-pi` |
| `ground-station/` | Link to the boat, database, web server, map building | Python | `ground-station` |
| `dashboard/` | The web page: video, map, readings, gamepad driving | HTML + JS | `dashboard` |
| `radio-testing/` | Radio setup, antenna, range tests, test logs | notes + scripts | `radio-testing` |
| `docs/` | Architecture, message formats, the master task list | markdown | `main` |

Every job folder has a `README.md` (what it is and how it fits) and a `TASKS.md` (the checklist for that job). Start there.

## Getting started

```bash
git clone https://github.com/gurujaya/ewbboat.git
cd ewbboat
git checkout boat-pi        # or whichever job is yours
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

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — how the whole thing works, from basic to advanced
- [docs/MESSAGES.md](docs/MESSAGES.md) — the four message types, field by field. Read this before writing any code that sends or receives anything.
- [docs/TASKS.md](docs/TASKS.md) — the master checklist across all jobs, by phase
- [docs/TESTING.md](docs/TESTING.md) — the tests each phase has to pass before we move on
