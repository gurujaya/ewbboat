// The 2-second safety watchdog (CLAUDE.md, "Safety first").
//
// If the Pi crashes, its USB cable falls out, or it starts sending garbage,
// the motors must stop on their own. feed() is called ONLY when a fully valid
// M line arrives; if 2000 ms pass without one, expired() turns true and the
// boat core cuts the motors and conveyor.
//
// Never make the timeout longer or switch this off to make a test pass. Send
// M lines from the test instead.

#pragma once

#include <stdint.h>

class Watchdog {
 public:
  static const uint32_t kTimeoutMs = 2000;

  Watchdog();

  // A valid M line just arrived at time now_ms.
  void feed(uint32_t now_ms);

  // True if no valid M line has arrived in the last 2000 ms (or ever).
  //
  // millis() wraps from 4294967295 back to 0 after about 49.7 days. We compare
  // with `now - last >= timeout` in unsigned math, which gives the right
  // answer across the wrap. Never write `now >= last + timeout`: that breaks
  // at the wrap.
  //
  // Once expired, it stays expired until the next feed(), even if the
  // subtraction would wrap around again after another 49 days of silence.
  bool expired(uint32_t now_ms);

 private:
  uint32_t last_feed_ms_;
  bool expired_;  // starts true: no command yet means motors off
};
