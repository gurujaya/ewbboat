// Turns a stream of serial bytes into whole lines.
//
// Serial data arrives a few bytes at a time, so we collect bytes in a small
// fixed buffer until we see '\n'. No heap, no String: the Uno has 2 KB of RAM
// and String fragments it.
//
// A line longer than the buffer is thrown away *entirely* (up to and
// including its '\n'). We never hand back half a line, because half of
// "M 0.45 0.75 1" could still look like a valid command.

#pragma once

#include <stddef.h>
#include <stdint.h>

class LineReader {
 public:
  // Longest line we accept, in characters. The longest valid M line is
  // "M -1.00 -1.00 1" (15 chars), so 47 leaves plenty of room.
  static const size_t kMaxLine = 47;

  LineReader();

  // Feed one byte. Returns true when a complete line has just ended; the
  // line (without '\n' or a trailing '\r') is then available from line()
  // until the next call to feed().
  bool feed(uint8_t b);

  const char* line() const { return buf_; }

 private:
  char buf_[kMaxLine + 1];  // +1 for the '\0' at the end
  size_t len_;
  bool too_long_;  // true while we are skipping the rest of an overlong line
};
