# testing tasks

Owners: Nicholas and Mir. Split the list between you and put your initials next to what you take.

## Phase 1: parts and prep
- [ ] Ask the club what it already has; write the inventory in `parts.md`
- [ ] Price what's missing (Pi, Arduino/ESP32, camera, GPS, compass, radios, SD cards, gamepad, waterproof box, pole); links in `parts.md`
- [ ] Send `parts.md` to Guru for the BOM
- [ ] Read `docs/TESTING.md`; ask about anything unclear
- [ ] Get the sensor models from Electrical; look up how each one is calibrated; draft `calibration.md`
- [ ] Buy or borrow calibration references (pH buffers, a thermometer, a known salt solution)

## Phase 2: table tests
- [ ] Log every table test in `docs/TESTING.md` as it's run (`logs/`)
- [ ] Watchdog test with Guru: pull the USB cable, motors stop within 2 s
- [ ] Heartbeat test with Eric: unplug the boat radio, dashboard says LINK LOST within 3 s
- [ ] Logging test: 5-minute run, compare station row count to the boat's CSV
- [ ] Take-control test with Sebastian: two devices, only one can drive

## Phase 3: calibration and water
- [ ] Calibrate all four sensors; numbers and photos in `calibration.md`
- [ ] Pool day: drive, go-to-waypoint, lost-signal, fence, fake low battery; a log file each
- [ ] Range test with Eric; log it
- [ ] Lake day with a rope: lost-signal for real, 1-hour run; log it
- [ ] First CSV into `analysis/`; battery-over-time and signal-vs-distance charts
- [ ] *Learn-as-you-go:* `analysis/plot.py` that makes those two charts from any CSV

## Phase 4: sweep and showcase
- [ ] Small sweep test; coverage map screenshot in the log
- [ ] Water-quality charts across the pond from the exported grid
- [ ] `demo.md`: run-of-show, who does what, backup plan
- [ ] Rehearse the demo once

## Always
- [ ] A log file for every test, the same day
- [ ] Engineering notebook entry every time something works for the first time
- [ ] `parts.md` updated whenever something is bought or found
