// Battery voltage: 5-second moving average, percent, low-battery warnings,
// and the 10 % motor cut (docs/ARCHITECTURE.md, "Low battery").
//
// Why average? A thruster starting up pulls the voltage down for a moment.
// Without averaging, that dip alone could trigger a low-battery warning.
//
// The voltages are PLACEHOLDERS until Electrical gives us the real pack
// curve. They match boat-pi/safety.py; change both together.

#pragma once

#include <stdint.h>

// PLACEHOLDER pack voltages (same as boat-pi/safety.py).
const float kBatteryVoltsFull = 12.6f;
const float kBatteryVoltsEmpty = 10.5f;

// Percent (0..100) from a voltage, as a straight line between empty and full.
float battery_percent(float volts);

// What the analog pin reading means in volts at the battery.
// raw: analogRead() result (0..adc_max). vref: the ADC reference voltage.
// divider_ratio: (R_top + R_bottom) / R_bottom of the resistor divider.
float adc_to_volts(uint16_t raw, uint16_t adc_max, float vref, float divider_ratio);

class Battery {
 public:
  static const uint8_t kSamples = 20;          // 20 samples ...
  static const uint16_t kSampleEveryMs = 250;  // ... every 250 ms = 5 s window
  static const uint8_t kCutPercent = 10;       // motors off at or below this

  Battery();

  // Call every loop with the latest reading (NaN if there is no reading).
  // It only takes a sample every 250 ms, so calling often is fine.
  void update(uint32_t now_ms, float volts);

  bool has_reading() const { return count_ > 0; }
  float average_volts() const;  // NaN until the first sample
  float percent() const;        // NaN until the first sample

  // True once for each warning threshold (30, 20, 10 %) the first time the
  // average drops to or below it. Call in a loop until it returns false:
  // a battery that starts at 5 % crosses all three at once.
  bool take_warning();

  // True once the average has reached 10 %. It stays true until the Arduino
  // restarts: a resting battery's voltage creeps back up when the motors stop,
  // and we don't want that to switch them back on (the boat would stutter
  // and drain the pack further). Restart after charging or swapping.
  bool motors_cut() const { return cut_; }

 private:
  float samples_[kSamples];  // ring buffer of recent readings
  uint8_t next_;             // where the next sample goes
  uint8_t count_;            // how many slots hold real samples (max kSamples)
  uint32_t last_sample_ms_;
  uint8_t warned_;           // bit 0 = 30 %, bit 1 = 20 %, bit 2 = 10 % already sent
  uint8_t pending_;          // warnings crossed but not yet taken
  bool cut_;
};
