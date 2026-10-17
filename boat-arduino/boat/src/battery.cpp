#include "battery.h"

#include <math.h>  // NAN

static const uint8_t kWarnPercents[3] = {30, 20, 10};

float battery_percent(float volts) {
  float pct = (volts - kBatteryVoltsEmpty) / (kBatteryVoltsFull - kBatteryVoltsEmpty) * 100.0f;
  if (pct < 0.0f) return 0.0f;
  if (pct > 100.0f) return 100.0f;
  return pct;
}

float adc_to_volts(uint16_t raw, uint16_t adc_max, float vref, float divider_ratio) {
  return (float)raw / (float)adc_max * vref * divider_ratio;
}

Battery::Battery() : next_(0), count_(0), last_sample_ms_(0), warned_(0), pending_(0), cut_(false) {
  for (uint8_t i = 0; i < kSamples; i++) samples_[i] = 0.0f;
}

void Battery::update(uint32_t now_ms, float volts) {
  if (volts != volts) return;  // NaN: no reading this time, keep what we have
  // Take the very first sample right away, then one every 250 ms.
  // (unsigned subtraction: safe when millis() wraps)
  if (count_ > 0 && (uint32_t)(now_ms - last_sample_ms_) < kSampleEveryMs) return;
  last_sample_ms_ = now_ms;

  samples_[next_] = volts;
  next_ = (uint8_t)((next_ + 1) % kSamples);
  if (count_ < kSamples) count_++;

  float pct = percent();
  for (uint8_t i = 0; i < 3; i++) {
    uint8_t bit = (uint8_t)(1u << i);
    if (pct <= (float)kWarnPercents[i] && !(warned_ & bit)) {
      warned_ |= bit;
      pending_++;
    }
  }
  if (pct <= (float)kCutPercent) cut_ = true;
}

float Battery::average_volts() const {
  if (count_ == 0) return NAN;
  float sum = 0.0f;
  for (uint8_t i = 0; i < count_; i++) sum += samples_[i];
  return sum / (float)count_;
}

float Battery::percent() const {
  if (count_ == 0) return NAN;
  return battery_percent(average_volts());
}

bool Battery::take_warning() {
  if (pending_ == 0) return false;
  pending_--;
  return true;
}
