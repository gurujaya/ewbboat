#include "line_reader.h"

LineReader::LineReader() : len_(0), too_long_(false) { buf_[0] = '\0'; }

bool LineReader::feed(uint8_t b) {
  if (b == '\n') {
    bool good = !too_long_;
    // The Arduino IDE serial monitor (and Windows tools) can end lines with
    // "\r\n". Drop one trailing '\r' so those lines still parse.
    if (len_ > 0 && buf_[len_ - 1] == '\r') len_--;
    buf_[good ? len_ : 0] = '\0';
    len_ = 0;
    too_long_ = false;  // the next line starts fresh
    return good;
  }

  if (too_long_) return false;  // still skipping an overlong line

  if (len_ >= kMaxLine) {
    // No room left: this line is garbage. Forget what we have and skip the
    // rest of it, so the next line after its '\n' is read cleanly.
    too_long_ = true;
    len_ = 0;
    return false;
  }

  buf_[len_++] = (char)b;
  return false;
}
