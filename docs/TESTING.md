# Testing

Three places, in order: table → pool → open water. Nothing goes on open water until it passed on the table and in the pool. Every water test has a rope on the boat or a kayak nearby; a stopped boat drifts.

Nicholas and Mir own running and logging these (`testing/`). Every test gets a file in `testing/logs/` the same day (template there); range tests also go in `comms/logs/`.

## In the simulator (before any of the below)

| Test | How | Passes when |
| --- | --- | --- |
| Unit tests | `python -m pytest` in `boat-pi`, `ground-station`, `comms`; `make -C boat-arduino test` | all pass |
| The math, many times | `python sim/montecarlo.py` (1 s) | every run passes its limits (row-tracking, fence, trip home, lost link) |
| The whole system | `python sim/headless_test.py` (10 min) | ALL PASS |

## Table tests (no water)

| Test | How | Passes when |
| --- | --- | --- |
| Serial loop | Pi sends `M 0.30 0.30 0`, Arduino echoes `T` lines | `T` lines arrive 5 times a second with sane values |
| Motor mixing | Push the gamepad stick forward, right, left, pull back | Motors spin the way `ARCHITECTURE.md` says for each |
| Watchdog | Motors running, pull the USB cable from the Arduino | Motors stop within 2 s, `E STOP_NO_PI` on reconnect |
| Heartbeat | Station and boat up, watch the dashboard | Boat marker green; unplug the boat's radio → "LINK LOST" within 3 s |
| Telemetry logging | Run 5 minutes, open the station DB and the boat CSV | Same number of rows (±5), every row has a timestamp and lat/lon |
| Video | Open the dashboard on a phone | Video plays, under ~1 s behind a hand wave in front of the camera |
| Take control | Two laptops open | Only the one that pressed Take control can move the motors |
| Battery thresholds | Feed a fake voltage into the Arduino (bench supply or a test flag) | Warning at 30 %, conveyor off + `COMING_HOME` at 20 %, motors off at 10 % |

## Pool tests

| Test | How | Passes when |
| --- | --- | --- |
| Drive | Forward, back, left, right, spin | Boat does what the stick says with no lag you can notice |
| Go to waypoint | Set one waypoint 10 m away, press Start sweep with a one-point list | Boat arrives within 2 m and stops; tune Kp until it doesn't zigzag |
| Hold a line | Sweep a 20 m × 6 m rectangle (3 rows). Compare the boat CSV's `lat`/`lon` (filtered) with the row lines | Straight part of each row within ~1 m of the line; no visible zig-zag. If it wiggles, lengthen `LOOKAHEAD_M`; if it drifts wide, shorten it or raise `KP` |
| GPS filter | Leave the boat tied up for 2 minutes, then drive a straight line. Plot `raw_lat`/`raw_lon` and `lat`/`lon` from the boat CSV | Filtered track visibly smoother than raw; `speed_mps` near 0 when tied up and steady on the straight |
| Lost signal | Drive out, power off the station radio | Boat stops, waits, drives back along its trail, stops at the launch spot |
| Fence | Set a small fence (sweep rectangle, or a small `DRIVEN_FENCE_M` in `boat-pi/config.py` for the test), drive across it | `fence_exit` event, boat stops, drives back to a point just inside, and hands control back (`DRIVEN`) or resumes the sweep (`AUTO`) |
| Low battery on water | Fake 20 % | Conveyor stops, boat heads home |
| Small sweep | 5 m × 5 m rectangle, 3 rows | All rows run, coverage map fills in, `sweep_done` fires |

## Open-water tests

| Test | How | Passes when |
| --- | --- | --- |
| Range | Station on the pole, walk/paddle the boat out, watch signal strength | We know the distance where signal drops below −80 dBm. That number becomes the DRIVEN fence radius. |
| Lost signal, real | Drive to the edge of range | Boat comes back on its own |
| 1 hour | Leave it sweeping or driving for an hour | Still linked, still logging at the end; battery % at the end written down |
| Full sweep | A real rectangle | Coverage map, heat map, and CSV export look right |

## What "written down" means

Date, who ran it, what was being tested, what happened, and one photo or screenshot. If it failed, what you think the cause is. Goes in the engineering notebook on OneDrive the same day.
