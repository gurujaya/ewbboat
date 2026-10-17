#include "m_line.h"

#include <stdint.h>

// We write our own number parser instead of using strtod/atof because those
// happily accept "nan", "inf", "1e3" and "0.5abc" (stopping at the junk).
// We want to reject all of those.
bool parse_plain_float(const char* s, unsigned len, float* out) {
  unsigned i = 0;
  bool negative = false;
  if (i < len && (s[i] == '+' || s[i] == '-')) {
    negative = (s[i] == '-');
    i++;
  }

  uint32_t whole = 0;
  unsigned whole_digits = 0;
  while (i < len && s[i] >= '0' && s[i] <= '9') {
    if (++whole_digits > 6) return false;  // far bigger than any command
    whole = whole * 10 + (uint32_t)(s[i] - '0');
    i++;
  }

  uint32_t frac = 0;
  uint32_t frac_scale = 1;
  unsigned frac_digits = 0;
  if (i < len && s[i] == '.') {
    i++;
    while (i < len && s[i] >= '0' && s[i] <= '9') {
      if (++frac_digits > 6) return false;
      frac = frac * 10 + (uint32_t)(s[i] - '0');
      frac_scale *= 10;
      i++;
    }
  }

  if (i != len) return false;                          // junk left over
  if (whole_digits + frac_digits == 0) return false;   // "", "-", "."

  float v = (float)whole + (float)frac / (float)frac_scale;
  *out = negative ? -v : v;
  return true;
}

static bool is_space(char c) { return c == ' ' || c == '\t'; }

bool parse_m_line(const char* line, MotorCommand* out) {
  // Split into tokens without copying: remember where each one starts and how
  // long it is. We need exactly 4; a 5th means the line is wrong.
  const char* tok[4];
  unsigned tok_len[4];
  unsigned count = 0;

  const char* p = line;
  while (true) {
    while (is_space(*p)) p++;
    if (*p == '\0') break;
    if (count == 4) return false;  // too many tokens
    tok[count] = p;
    while (*p != '\0' && !is_space(*p)) p++;
    tok_len[count] = (unsigned)(p - tok[count]);
    count++;
  }
  if (count != 4) return false;

  if (tok_len[0] != 1 || tok[0][0] != 'M') return false;

  float left, right;
  if (!parse_plain_float(tok[1], tok_len[1], &left)) return false;
  if (!parse_plain_float(tok[2], tok_len[2], &right)) return false;
  if (left < -1.0f || left > 1.0f) return false;
  if (right < -1.0f || right > 1.0f) return false;

  if (tok_len[3] != 1 || (tok[3][0] != '0' && tok[3][0] != '1')) return false;

  out->left = left;
  out->right = right;
  out->conveyor = (tok[3][0] == '1');
  return true;
}
