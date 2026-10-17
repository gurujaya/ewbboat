// The hardware boundary ("HAL" = hardware abstraction layer).
//
// Everything in src/ is plain C++ that never touches a pin. It talks to the
// outside world only through the two things in this file:
//
//   SensorReadings  what the sensors say right now (filled in by the caller)
//   BoatHal         where serial text and motor outputs go
//
// On the boat, boat.ino fills SensorReadings from the real GPS/compass/ADC and
// implements BoatHal with Serial.print() and analogWrite(). In the simulator,
// host/host_main.cpp fills them from the physics model and prints to stdout.
// The logic in between (parsing, watchdog, battery rules, T lines) is the
// same compiled code in both places.

#pragma once

#include <stdint.h>

struct SensorReadings {
  // GPS. Position is stored as millionths of a degree in a whole number
  // because a float on the Uno only has ~7 significant digits: 39.091234
  // would come out as 39.09123x, which is up to ~0.5 m off.
  bool gps_fix;      // true when the GPS has a position fix
  int32_t lat_udeg;  // latitude  * 1,000,000 (only used when gps_fix)
  int32_t lon_udeg;  // longitude * 1,000,000 (only used when gps_fix)
  uint8_t sats;      // satellites in view, 0 if unknown

  float heading_deg;  // compass, 0-360 clockwise from north; NaN if no compass
  float batt_v;       // battery volts (after undoing the divider); NaN if not read

  // Water sensors; NaN when the sensor isn't connected yet.
  float temp_c;
  float ph;
  float turb_ntu;
  float cond_us;
};

class BoatHal {
 public:
  // Send text to the Pi exactly as given (it already ends in '\n').
  virtual void write_serial(const char* text) = 0;

  // Drive the thrusters (-1..+1 each) and the conveyor (on/off).
  // Called on every step, so the outputs are always re-applied.
  virtual void set_motors(float left, float right, bool conveyor) = 0;

 protected:
  ~BoatHal() {}  // never deleted through this pointer; no heap on the Uno
};
