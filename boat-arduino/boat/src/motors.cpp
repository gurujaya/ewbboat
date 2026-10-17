#include "motors.h"

float clamp_unit(float v) {
  if (v != v) return 0.0f;  // NaN
  if (v < -1.0f) return -1.0f;
  if (v > 1.0f) return 1.0f;
  return v;
}

MotorDrive motor_to_drive(float command) {
  float c = clamp_unit(command);
  MotorDrive d;
  d.forward = c >= 0.0f;
  float mag = d.forward ? c : -c;
  d.pwm = (uint8_t)(mag * 255.0f + 0.5f);  // round to nearest step
  return d;
}
