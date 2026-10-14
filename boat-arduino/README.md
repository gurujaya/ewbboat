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

## Layout (to create)

```
boat-arduino/
  boat.ino          setup() and loop(); timing with millis(), no delay()
  motors.h/.cpp     scale -1..+1 to the driver, apply, emergency stop
  sensors.h/.cpp    read the four water sensors, averaging, calibration constants
  gps.h/.cpp        parse NMEA, expose lat/lon/fix/sats
  compass.h/.cpp    heading in degrees, 0-360 clockwise from north, with declination offset
  battery.h/.cpp    read voltage, 5 s moving average, percent, thresholds
  serial_link.h/.cpp  parse M lines, build T and E lines, the watchdog
  calibration.md    where the sensor calibration numbers came from and when
```

## Setup

1. Install the Arduino IDE (or PlatformIO in VS Code).
2. Board: TBD (Arduino Uno/Mega or ESP32; decide in phase 1).
3. Libraries: TinyGPS++ (GPS), a compass library matching the module Electrical picks.
4. Open `boat.ino`, pick the board and port, upload.
5. Open the serial monitor at 115200. You should see `T` lines once a second.

## Things to never change

- The watchdog stays at 2 s and stays on. If a test is annoying because of it, send heartbeats, don't disable it.
- Motor commands only come from `M` lines. No other path.
- The 10 % battery motor cut is enforced here too, so it works even if the Pi is dead.
