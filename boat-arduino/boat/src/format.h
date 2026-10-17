// Number-to-text helpers for building T and E lines.
//
// Why not snprintf("%.2f")? On the Uno (avr-libc), printf has no %f support
// by default: it prints "?" instead of the number. So we format floats
// ourselves with plain integer math, which works the same on every board and
// on the laptop.

#pragma once

#include <stddef.h>
#include <stdint.h>

// Writes `v` with exactly `decimals` digits after the point (0..6), rounding
// half away from zero: format_fixed(12.104, 2) -> "12.10", (-0.5, 0) -> "-1".
// NaN, infinity, or a number too big for our integer math (|v| * 10^decimals
// over ~4 billion) is written as "nan", which is what the protocol uses for
// "no reading". "-0.00" is written as "0.00".
// Always '\0'-terminates (if cap > 0). Returns the length written.
size_t format_fixed(float v, uint8_t decimals, char* out, size_t cap);

// Writes a coordinate stored as millionths of a degree, e.g.
// 39091230 -> "39.091230", -77153400 -> "-77.153400".
size_t format_udeg(int32_t udeg, char* out, size_t cap);

// Appends text into a fixed char buffer and never writes past the end.
// If something doesn't fit, overflowed() turns true and the line should not
// be sent (a cut-off T line would have the wrong number of fields).
class LineBuilder {
 public:
  LineBuilder(char* buf, size_t cap);

  void add(const char* s);
  void add_char(char c);
  void add_fixed(float v, uint8_t decimals);
  void add_udeg(int32_t udeg);
  void add_uint(uint32_t v);
  void add_nan() { add("nan"); }

  const char* str() const { return buf_; }
  size_t length() const { return len_; }
  bool overflowed() const { return overflow_; }

 private:
  char* buf_;
  size_t cap_;
  size_t len_;
  bool overflow_;
};
