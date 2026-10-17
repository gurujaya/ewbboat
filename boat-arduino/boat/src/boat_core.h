// BoatCore: everything the Arduino decides, in one place, with no pins.
//
// How it's used (boat.ino on the board, host_main.cpp in the simulator):
//
//   BoatCore core(hal);
//   loop:
//     for each byte from the Pi:  core.on_serial_byte(byte, millis());
//     read the sensors into a SensorReadings
//     core.step(millis(), readings);   // sets motors, sends T/E lines
//
// What step() does, in order:
//   1. battery: take a sample for the 5 s average
//   2. decide the motor outputs:
//        - watchdog expired (no valid M line for 2 s)  -> all off
//        - battery at or below 10 %                    -> all off
//        - otherwise                                   -> the last M line
//      and apply them through the HAL (every step, so a glitch can't stick)
//   3. send E lines for anything that just happened:
//        STOP_NO_PI (once per silence), BATT_LOW (once per 30/20/10 %),
//        GPS_LOST (fix went from 1 to 0)
//   4. five times a second (every 200 ms), send a T line

#pragma once

#include <stdint.h>

#include "battery.h"
#include "hal.h"
#include "line_reader.h"
#include "m_line.h"
#include "watchdog.h"

class BoatCore {
 public:
  // 5 Hz: the Pi's autopilot steers on GPS + compass, and a 1 Hz heading is too
  // stale to steer a turning boat with. docs/MESSAGES.md, "USB serial".
  static const uint32_t kTelemetryEveryMs = 200;

  explicit BoatCore(BoatHal& hal);

  // One byte from the Pi's serial line, received at now_ms.
  void on_serial_byte(uint8_t b, uint32_t now_ms);

  // Run the rules once. Call this every loop().
  void step(uint32_t now_ms, const SensorReadings& sensors);

  // Read-only views, handy for tests.
  const MotorCommand& command() const { return cmd_; }
  const Battery& battery() const { return battery_; }

 private:
  void handle_line(const char* line, uint32_t now_ms);
  void send_event(const char* code);
  void send_telemetry(const SensorReadings& s);

  BoatHal& hal_;
  LineReader reader_;
  Watchdog watchdog_;
  Battery battery_;
  MotorCommand cmd_;           // the last valid M line (zeros until one arrives)
  bool stop_event_armed_;      // send STOP_NO_PI on the next watchdog expiry
  bool prev_fix_;              // GPS fix on the previous step, to spot a drop
  bool telemetry_started_;     // false until the first T line is sent
  uint32_t last_telemetry_ms_;
};
