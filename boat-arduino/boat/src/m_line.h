// Parses the Pi's motor command: "M <left> <right> <conveyor>"
// (docs/MESSAGES.md, "USB serial").
//
// Strict on purpose. Only a line that is exactly right counts, because a valid
// M line is also what keeps the 2-second watchdog happy. If line noise could
// sneak through as a command, a dead Pi plus a noisy cable could keep the
// motors running.

#pragma once

struct MotorCommand {
  float left;     // -1..+1, negative = backwards
  float right;    // -1..+1
  bool conveyor;  // on/off
};

// Returns true and fills *out only if `line` is a valid M line:
//   - exactly 4 tokens separated by spaces/tabs
//   - first token is exactly "M"
//   - left and right are plain decimal numbers (like 0.45, -1, .5) in [-1, +1]
//     (no "nan", "inf", exponents, or junk after the number)
//   - conveyor is exactly "0" or "1"
// On false, *out is left untouched.
bool parse_m_line(const char* line, MotorCommand* out);

// The number parser parse_m_line uses, exposed so the tests can poke it.
// Reads exactly `len` characters. Accepts an optional sign, up to 6 digits
// before and 6 after a '.', and at least one digit somewhere.
bool parse_plain_float(const char* s, unsigned len, float* out);
