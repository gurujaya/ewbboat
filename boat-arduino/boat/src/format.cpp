#include "format.h"

// Copies a '\0'-terminated string, cutting it off if needed.
static size_t copy_str(const char* s, char* out, size_t cap) {
  if (cap == 0) return 0;
  size_t n = 0;
  while (s[n] != '\0' && n + 1 < cap) {
    out[n] = s[n];
    n++;
  }
  out[n] = '\0';
  return n;
}

// Writes an unsigned integer, padded with leading zeros to at least
// `min_digits` digits. Returns the length, or 0 if it didn't fit.
static size_t write_uint(uint32_t v, unsigned min_digits, char* out, size_t cap) {
  char rev[11];  // 4294967295 has 10 digits
  unsigned n = 0;
  do {
    rev[n++] = (char)('0' + v % 10);
    v /= 10;
  } while (v > 0);
  while (n < min_digits && n < sizeof(rev)) rev[n++] = '0';
  if (n + 1 > cap) return 0;
  for (unsigned i = 0; i < n; i++) out[i] = rev[n - 1 - i];
  out[n] = '\0';
  return n;
}

size_t format_fixed(float v, uint8_t decimals, char* out, size_t cap) {
  if (cap == 0) return 0;
  if (decimals > 6) decimals = 6;

  // NaN is the only value that isn't equal to itself. (We avoid isnan() so
  // this file needs nothing beyond the C basics on every board.)
  if (v != v) return copy_str("nan", out, cap);

  bool negative = v < 0.0f;
  float mag = negative ? -v : v;

  uint32_t scale = 1;
  for (uint8_t i = 0; i < decimals; i++) scale *= 10;

  // Everything below happens in whole numbers: 12.104 with 2 decimals becomes
  // 1210 (rounded), then we print "12" "." "10".
  float scaled = mag * (float)scale + 0.5f;
  if (!(scaled < 4.0e9f)) return copy_str("nan", out, cap);  // too big (or inf)
  uint32_t n = (uint32_t)scaled;
  if (n == 0) negative = false;  // don't print "-0.00"

  size_t len = 0;
  if (negative) {
    if (cap < 2) return copy_str("nan", out, cap);
    out[len++] = '-';
  }
  size_t w = write_uint(n / scale, 1, out + len, cap - len);
  if (w == 0) return copy_str("nan", out, cap);
  len += w;
  if (decimals > 0) {
    if (len + 1 >= cap) return copy_str("nan", out, cap);
    out[len++] = '.';
    w = write_uint(n % scale, decimals, out + len, cap - len);
    if (w == 0) return copy_str("nan", out, cap);
    len += w;
  }
  return len;
}

size_t format_udeg(int32_t udeg, char* out, size_t cap) {
  if (cap == 0) return 0;
  // Work with the size as unsigned so even the most negative int32 is safe.
  uint32_t mag = udeg < 0 ? (uint32_t)0 - (uint32_t)udeg : (uint32_t)udeg;
  size_t len = 0;
  if (udeg < 0) {
    if (cap < 2) return copy_str("nan", out, cap);
    out[len++] = '-';
  }
  size_t w = write_uint(mag / 1000000UL, 1, out + len, cap - len);
  if (w == 0) return copy_str("nan", out, cap);
  len += w;
  if (len + 1 >= cap) return copy_str("nan", out, cap);
  out[len++] = '.';
  w = write_uint(mag % 1000000UL, 6, out + len, cap - len);
  if (w == 0) return copy_str("nan", out, cap);
  return len + w;
}

// ---- LineBuilder ----------------------------------------------------------

LineBuilder::LineBuilder(char* buf, size_t cap) : buf_(buf), cap_(cap), len_(0), overflow_(cap == 0) {
  if (cap_ > 0) buf_[0] = '\0';
}

void LineBuilder::add(const char* s) {
  while (*s != '\0') add_char(*s++);
}

void LineBuilder::add_char(char c) {
  if (overflow_ || len_ + 1 >= cap_) {
    overflow_ = true;
    return;
  }
  buf_[len_++] = c;
  buf_[len_] = '\0';
}

void LineBuilder::add_fixed(float v, uint8_t decimals) {
  char tmp[16];
  format_fixed(v, decimals, tmp, sizeof(tmp));
  add(tmp);
}

void LineBuilder::add_udeg(int32_t udeg) {
  char tmp[16];
  format_udeg(udeg, tmp, sizeof(tmp));
  add(tmp);
}

void LineBuilder::add_uint(uint32_t v) {
  char tmp[12];
  write_uint(v, 1, tmp, sizeof(tmp));
  add(tmp);
}
