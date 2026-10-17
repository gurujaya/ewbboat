// Turning a motor command (-1..+1) into what a motor driver wants.
//
// Most cheap drivers take a direction pin (forward/backward) and a PWM pin
// (0..255 = how hard). The real driver is TBD by Electrical; if it wants
// something else (an RC-style ESC pulse, for example) only this file and the
// pin code in boat.ino change.

#pragma once

#include <stdint.h>

struct MotorDrive {
  uint8_t pwm;   // 0..255 for analogWrite()
  bool forward;  // direction pin level
};

// Keeps a value inside -1..+1. NaN becomes 0 (stopped), the safe choice.
float clamp_unit(float v);

// -1..+1 -> direction + PWM duty. 0.5 -> forward, 128. -1 -> backward, 255.
MotorDrive motor_to_drive(float command);
