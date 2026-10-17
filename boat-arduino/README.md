# boat-arduino

The firmware on the boat's Arduino. It does, it doesn't think: runs the motors and conveyor, reads the sensors, and cuts the motors if the Pi goes quiet.

Owner: **Guru Jayaprakash** (`gurujaya`), with John (Electrical) for pins and drivers. Branch: `boat-arduino`. Language: C++ (Arduino IDE or PlatformIO).

## What it owns

- Two thruster motors through a motor driver (pins TBD from Electrical)
- One conveyor gearmotor, on/off
- Four water sensors: temperature, pH, turbidity, conductivity
- GPS module (UART), compass/IMU (I2C)
- Battery voltage through a divider on an analog pin
- The 2-second watchdog: no valid `M` line from the Pi → motors and conveyor off

## What it talks to

Only the Pi, over USB serial at 115200. Formats are in [`../docs/MESSAGES.md`](../docs/MESSAGES.md), section "USB serial".

- Receives `M <left> <right> <conveyor>` 10×/s
- Sends `T <lat> <lon> <heading> <fix> <sats> <batt_v> <temp> <ph> <turb> <cond>` 1×/s
- Sends `E <code>` on events

## Layout

```
boat-arduino/
  boat/                    the sketch (Arduino needs the folder name to match the .ino)
    boat.ino               the hardware part: pins, Serial, sensor reads; setup()/loop() with millis(), no delay()
    src/                   all the decisions, in plain C++ with no Arduino code (the IDE compiles src/ automatically)
      hal.h                the boundary: SensorReadings in, serial text + motor outputs out
      boat_core.h/.cpp     ties it together: bytes in, step(now_ms, sensors) -> motors, T and E lines
      line_reader.h/.cpp   collects serial bytes into lines; throws away overlong ones
      m_line.h/.cpp        strict parser for "M <left> <right> <conveyor>"
      watchdog.h/.cpp      the 2 s watchdog (safe when millis() wraps after 49 days)
      battery.h/.cpp       5 s moving average, percent, 30/20/10 % warnings, 10 % motor cut
      telemetry.h/.cpp     builds T and E lines
      format.h/.cpp        float -> text (the Uno's printf can't do %f)
      motors.h/.cpp        -1..+1 -> direction + PWM
  host/host_main.cpp       the same src/ logic, built for a laptop, for the simulator
  tests/test_core.cpp      unit tests for src/
  Makefile                 `make test`, `make host`
  calibration.md           (to create) where the sensor calibration numbers came from and when
```

**Why split it like this?** Everything that *decides* something lives in `src/` and never touches a pin, so it compiles on the laptop too. That buys two things: the unit tests run in a second without a board, and the simulator (`../sim`) runs this exact code instead of a Python copy of it. Only `boat.ino` is different on the boat: it reads real pins and sensors and drives the real motor driver. If you change a rule (the watchdog, battery thresholds, the T line), change it in `src/` and both the boat and the sim get it.

Rules for `src/`: no `#include <Arduino.h>`, no `String`, no `new`/`malloc`, no STL. The Uno has 2 KB of RAM. It must compile both with the Arduino toolchain (C++11) and with `clang++/g++ -std=c++17`.

## Still placeholders

- **Pins and motor driver** (`boat.ino`, top): direction pin + PWM pin per thruster, one pin for the conveyor. Change when Electrical decides.
- **Battery divider** `DIVIDER_RATIO` and the full/empty voltages (`src/battery.h`, same numbers as `boat-pi/safety.py`; change both together).
- **GPS, compass, water sensors**: stubs that report "no fix" / `nan`. The T line already sends `nan` for them, as the protocol says. Each stub has a TODO naming the planned library.
- **Board**: compiles for both Uno and Mega today (Uno: about 7.7 KB flash, 407 bytes RAM for globals). A Mega gives a spare hardware serial port for the GPS.

## Setup

1. Install the Arduino IDE (or `arduino-cli`, or PlatformIO in VS Code).
2. Board: TBD (Arduino Uno/Mega or ESP32; decide in phase 1).
3. Libraries: none yet. Later: TinyGPS++ (GPS), a compass library matching the module Electrical picks.
4. Open `boat/boat.ino`, pick the board and port, upload. Or from the repo root:
   ```bash
   arduino-cli core install arduino:avr      # once
   arduino-cli compile --fqbn arduino:avr:uno boat-arduino/boat
   arduino-cli upload  --fqbn arduino:avr:uno -p /dev/ttyUSB0 boat-arduino/boat
   ```
5. Open the serial monitor at 115200. You should see `T` lines 5 times a second (`nan` for sensors not wired yet). Type `M 0.5 0.5 0` and press enter a few times: the motors run, then stop 2 s after you stop typing, and you'll see `E STOP_NO_PI`.

## Tests

```bash
make -C boat-arduino test      # from the repo root; needs a C++ compiler (macOS: xcode-select --install, Linux: apt install g++ make)
```

They cover M line parsing (good and bad lines), number formatting (`nan`, negatives, rounding), the watchdog (including when `millis()` wraps), battery warnings firing once each, the 10 % cut, `STOP_NO_PI` once per silence, and that garbage or overlong lines never keep the motors running. Add a test when you change a rule in `src/`.

## The laptop build (for the simulator)

`make -C boat-arduino host` builds `build/boat-host`: the `src/` logic plus `host/host_main.cpp`, which plays the part of `boat.ino` using text on stdin/stdout instead of pins. `sim/fake_arduino.py` runs it, feeds it the Pi's serial bytes and the fake sensor readings from the physics model, and moves the fake boat with the motor outputs it returns. `sim/run.py` builds it for you (and rebuilds it when `src/` changes), so you normally never run this by hand. The protocol is described at the top of `host/host_main.cpp`.

## Things to never change

- The watchdog stays at 2 s and stays on. If a test is annoying because of it, send heartbeats, don't disable it.
- Motor commands only come from `M` lines. No other path.
- The 10 % battery motor cut is enforced here too, so it works even if the Pi is dead.
