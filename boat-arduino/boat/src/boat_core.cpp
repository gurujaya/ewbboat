#include "boat_core.h"

#include "telemetry.h"

BoatCore::BoatCore(BoatHal& hal)
    : hal_(hal),
      stop_event_armed_(false),
      prev_fix_(false),
      telemetry_started_(false),
      last_telemetry_ms_(0) {
  cmd_.left = 0.0f;
  cmd_.right = 0.0f;
  cmd_.conveyor = false;
}

void BoatCore::on_serial_byte(uint8_t b, uint32_t now_ms) {
  if (reader_.feed(b)) handle_line(reader_.line(), now_ms);
}

void BoatCore::handle_line(const char* line, uint32_t now_ms) {
  MotorCommand c;
  // Only a fully valid M line counts. Anything else (noise, a half line, a
  // number out of range) is ignored and does NOT feed the watchdog.
  if (!parse_m_line(line, &c)) return;
  cmd_ = c;
  watchdog_.feed(now_ms);
  stop_event_armed_ = true;  // if the Pi goes quiet after this, say so once
}

void BoatCore::step(uint32_t now_ms, const SensorReadings& s) {
  // 1. battery average
  battery_.update(now_ms, s.batt_v);

  // 2. motors. Safety first, before any slow serial writes.
  bool pi_silent = watchdog_.expired(now_ms);
  if (pi_silent) {
    // Forget the old command, so nothing old can come back to life.
    cmd_.left = 0.0f;
    cmd_.right = 0.0f;
    cmd_.conveyor = false;
  }
  if (pi_silent || battery_.motors_cut()) {
    hal_.set_motors(0.0f, 0.0f, false);
  } else {
    hal_.set_motors(cmd_.left, cmd_.right, cmd_.conveyor);
  }

  // 3. events
  if (pi_silent && stop_event_armed_) {
    send_event("STOP_NO_PI");
    stop_event_armed_ = false;  // once per silence; a valid M line re-arms it
  }
  while (battery_.take_warning()) send_event("BATT_LOW");
  if (prev_fix_ && !s.gps_fix) send_event("GPS_LOST");
  prev_fix_ = s.gps_fix;

  // 4. telemetry every kTelemetryEveryMs (unsigned subtraction: safe when millis() wraps)
  if (!telemetry_started_ || (uint32_t)(now_ms - last_telemetry_ms_) >= kTelemetryEveryMs) {
    telemetry_started_ = true;
    last_telemetry_ms_ = now_ms;
    send_telemetry(s);
  }
}

void BoatCore::send_event(const char* code) {
  char line[24];
  if (build_e_line(code, line, sizeof(line))) hal_.write_serial(line);
}

void BoatCore::send_telemetry(const SensorReadings& s) {
  char line[kMaxOutLine];
  if (build_t_line(s, battery_.average_volts(), line, sizeof(line))) hal_.write_serial(line);
}
