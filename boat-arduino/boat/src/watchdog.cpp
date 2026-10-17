#include "watchdog.h"

Watchdog::Watchdog() : last_feed_ms_(0), expired_(true) {}

void Watchdog::feed(uint32_t now_ms) {
  last_feed_ms_ = now_ms;
  expired_ = false;
}

bool Watchdog::expired(uint32_t now_ms) {
  if (!expired_ && (uint32_t)(now_ms - last_feed_ms_) >= kTimeoutMs) expired_ = true;
  return expired_;
}
