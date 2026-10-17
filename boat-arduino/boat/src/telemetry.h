// Builds the lines the Arduino sends to the Pi (docs/MESSAGES.md, "USB serial"):
//
//   T <lat> <lon> <heading> <fix> <sats> <batt_v> <temp> <ph> <turb> <cond>\n
//   E <code>\n
//
// boat-pi/arduino.py expects exactly 11 fields in a T line. Anything we don't
// have is sent as "nan".

#pragma once

#include <stddef.h>

#include "hal.h"

// Room for the longest possible T line, e.g.
// "T -89.999999 -179.999999 359.9 1 255 99999.99 99999.9 99999.99 99999.9 9999999\n"
const size_t kMaxOutLine = 96;

// Decimals per field: lat/lon 6, heading 1, batt 2, temp 1, ph 2, turb 1, cond 0.
// batt_avg_v is the averaged battery voltage (NaN if none yet).
// Returns false if the line didn't fit in `cap` (then don't send it).
bool build_t_line(const SensorReadings& s, float batt_avg_v, char* out, size_t cap);

// "E <code>\n". Returns false if it didn't fit.
bool build_e_line(const char* code, char* out, size_t cap);
