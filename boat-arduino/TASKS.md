# boat-arduino tasks

Tick in the same commit that finishes the work.

## Phase 1
- [ ] Decide Arduino vs ESP32 with the team
- [ ] Get the pin list and motor driver model from Electrical
- [ ] Get the sensor models from Electrical; write them in README
- [ ] Set up the IDE, blink an LED, commit the empty sketch

## Phase 2: table
- [x] Firmware logic as portable C++ in `boat/src/` with unit tests (`make test`), built for the laptop so the sim runs it
- [x] Parse `M` lines; reject malformed ones
- [ ] Drive both motors from `left`/`right`; test straight, turn, spin on the bench
- [ ] Conveyor on/off from the `M` line
- [x] Watchdog: no `M` for 2 s → all off, send `E STOP_NO_PI`
- [ ] Read GPS, send lat/lon/fix/sats in the `T` line
- [ ] Read compass, 0-360 clockwise from north; set the local magnetic declination
- [ ] Read battery voltage; 5 s moving average
- [x] Send a `T` line once a second with `nan` for sensors not yet connected
- [x] `T` line at 5 Hz (200 ms) so the Pi's autopilot steers on fresh GPS + compass; set the real GPS module to 5 Hz too
- [ ] Test: full `M`/`T` loop with the Pi on the table

## Phase 3: safety and sensors
- [ ] Wire and read all four water sensors
- [ ] Calibrate each one; write the numbers and the method in `calibration.md`
- [ ] Battery percent from voltage, using Electrical's real pack curve
- [x] 10 % motor cut enforced here; `E BATT_LOW` on each threshold
- [x] `E GPS_LOST` when the fix drops
- [ ] Test: watchdog by pulling the USB cable (motors stop within 2 s)
- [ ] Test: fake battery voltage walks through 30/20/10 %

## Phase 4
- [ ] Nothing new here; autopilot lives on the Pi. Help tune motor scaling so `left = right` really goes straight.

## Always
- [ ] Every wiring change goes in README with a date
