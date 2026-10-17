// Unit tests for the firmware logic in boat/src/. Runs on the laptop:
//
//   make -C boat-arduino test
//
// Plain checks, no test framework. Each CHECK prints the line on failure;
// the program exits non-zero if anything failed.

#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "../boat/src/battery.h"
#include "../boat/src/boat_core.h"
#include "../boat/src/format.h"
#include "../boat/src/line_reader.h"
#include "../boat/src/m_line.h"
#include "../boat/src/motors.h"
#include "../boat/src/telemetry.h"
#include "../boat/src/watchdog.h"

static int g_failed = 0;
static int g_passed = 0;

#define CHECK(cond)                                                    \
  do {                                                                 \
    if (cond) {                                                        \
      g_passed++;                                                      \
    } else {                                                           \
      g_failed++;                                                      \
      std::printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #cond);      \
    }                                                                  \
  } while (0)

#define CHECK_STR(actual, expected)                                                         \
  do {                                                                                      \
    std::string a_ = (actual), e_ = (expected);                                             \
    if (a_ == e_) {                                                                         \
      g_passed++;                                                                           \
    } else {                                                                                \
      g_failed++;                                                                           \
      std::printf("FAIL %s:%d  got \"%s\", want \"%s\"\n", __FILE__, __LINE__, a_.c_str(), \
                  e_.c_str());                                                              \
    }                                                                                       \
  } while (0)

// ---- helpers ------------------------------------------------------------------

// A HAL that remembers everything, instead of driving pins.
struct FakeHal : public BoatHal {
  std::vector<std::string> lines;  // everything written to serial
  float left = 99, right = 99;     // 99 = never set
  bool conveyor = false;

  void write_serial(const char* text) override { lines.push_back(text); }
  void set_motors(float l, float r, bool c) override {
    left = l;
    right = r;
    conveyor = c;
  }
  int count(const std::string& line) const {
    int n = 0;
    for (const auto& l : lines) n += (l == line);
    return n;
  }
};

static void send(BoatCore& core, const std::string& text, uint32_t now_ms) {
  for (char c : text) core.on_serial_byte((uint8_t)c, now_ms);
}

static SensorReadings good_sensors(float batt_v = 12.6f) {
  SensorReadings s;
  s.gps_fix = true;
  s.lat_udeg = 39091230;
  s.lon_udeg = -77153400;
  s.sats = 9;
  s.heading_deg = 212.5f;
  s.batt_v = batt_v;
  s.temp_c = 21.4f;
  s.ph = 7.6f;
  s.turb_ntu = 12.0f;
  s.cond_us = 410.0f;
  return s;
}

static std::string fixed(float v, int decimals) {
  char buf[24];
  format_fixed(v, (uint8_t)decimals, buf, sizeof(buf));
  return buf;
}

static std::string udeg(int32_t v) {
  char buf[24];
  format_udeg(v, buf, sizeof(buf));
  return buf;
}

static bool parses(const char* line) {
  MotorCommand c;
  return parse_m_line(line, &c);
}

// ---- M line parsing -------------------------------------------------------------

static void test_m_parse() {
  MotorCommand c;
  CHECK(parse_m_line("M 0.45 0.75 1", &c));
  CHECK(std::fabs(c.left - 0.45f) < 1e-6f && std::fabs(c.right - 0.75f) < 1e-6f && c.conveyor);
  CHECK(parse_m_line("M -1.00 1.00 0", &c));
  CHECK(c.left == -1.0f && c.right == 1.0f && !c.conveyor);
  CHECK(parses("M 0 0 0"));
  CHECK(parses("M -0.00 +0.5 0"));
  CHECK(parses("M .5 -.25 1"));
  CHECK(parses("  M\t0.1  0.2 0  "));  // extra spaces/tabs are fine

  // rejects
  CHECK(!parses(""));
  CHECK(!parses("M"));
  CHECK(!parses("M 0.1 0.2"));          // 3 tokens
  CHECK(!parses("M 0.1 0.2 1 5"));      // 5 tokens
  CHECK(!parses("m 0.1 0.2 1"));        // lowercase
  CHECK(!parses("MM 0.1 0.2 1"));
  CHECK(!parses("T 0.1 0.2 1"));
  CHECK(!parses("M 1.01 0 0"));         // out of range
  CHECK(!parses("M 0 -1.5 0"));
  CHECK(!parses("M 0 0 2"));            // conveyor must be 0/1
  CHECK(!parses("M 0 0 01"));
  CHECK(!parses("M 0 0 1.0"));
  CHECK(!parses("M nan 0 0"));
  CHECK(!parses("M inf 0 0"));
  CHECK(!parses("M 1e-1 0 0"));         // no exponents
  CHECK(!parses("M 0.5abc 0 0"));       // junk after the number
  CHECK(!parses("M - 0 0"));
  CHECK(!parses("M . 0 0"));
  CHECK(!parses("M 0..5 0 0"));
  CHECK(!parses("M 0.1234567 0 0"));    // more than 6 decimals
  CHECK(!parses("M 0,5 0 0"));

  // a rejected line leaves the output alone
  c.left = 0.3f;
  CHECK(!parse_m_line("M 9 9 9", &c));
  CHECK(c.left == 0.3f);
}

// ---- line reader ------------------------------------------------------------------

static void test_line_reader() {
  LineReader r;
  const char* text = "M 0.1 0.2 1\n";
  int ready = 0;
  for (const char* p = text; *p; p++) ready += r.feed((uint8_t)*p);
  CHECK(ready == 1);
  CHECK_STR(r.line(), "M 0.1 0.2 1");

  // "\r\n" endings work
  for (const char* p = "M 0 0 0\r\n"; *p; p++) r.feed((uint8_t)*p);
  CHECK_STR(r.line(), "M 0 0 0");

  // an overlong line is thrown away entirely, the next one is read cleanly
  std::string longline(200, '7');
  longline = "M 0.1 0.2 1" + longline + "\n";
  ready = 0;
  for (char c : longline) ready += r.feed((uint8_t)c);
  CHECK(ready == 0);
  for (const char* p = "M 0.3 0.4 0\n"; *p; p++) ready += r.feed((uint8_t)*p);
  CHECK(ready == 1);
  CHECK_STR(r.line(), "M 0.3 0.4 0");

  // exactly kMaxLine characters still fits; one more doesn't
  std::string fits(LineReader::kMaxLine, 'x');
  ready = 0;
  for (char c : fits + "\n") ready += r.feed((uint8_t)c);
  CHECK(ready == 1);
  ready = 0;
  for (char c : fits + "y\n") ready += r.feed((uint8_t)c);
  CHECK(ready == 0);
}

// ---- number formatting ------------------------------------------------------------

static void test_format() {
  CHECK_STR(fixed(12.1f, 2), "12.10");
  CHECK_STR(fixed(212.5f, 1), "212.5");
  CHECK_STR(fixed(410.0f, 0), "410");
  CHECK_STR(fixed(0.0f, 2), "0.00");
  CHECK_STR(fixed(7.6f, 2), "7.60");
  CHECK_STR(fixed(-3.25f, 1), "-3.3");      // half rounds away from zero
  CHECK_STR(fixed(0.125f, 2), "0.13");
  CHECK_STR(fixed(0.996f, 2), "1.00");      // rounding carries into the whole part
  CHECK_STR(fixed(9.96f, 1), "10.0");
  CHECK_STR(fixed(-0.004f, 2), "0.00");     // no "-0.00"
  CHECK_STR(fixed(-12.5f, 0), "-13");
  CHECK_STR(fixed(-0.05f, 2), "-0.05");
  CHECK_STR(fixed(0.000001f, 6), "0.000001");
  CHECK_STR(fixed(NAN, 2), "nan");
  CHECK_STR(fixed(INFINITY, 1), "nan");
  CHECK_STR(fixed(-INFINITY, 1), "nan");
  CHECK_STR(fixed(1e12f, 2), "nan");        // too big for the integer math

  CHECK_STR(udeg(39091230), "39.091230");
  CHECK_STR(udeg(-77153400), "-77.153400");
  CHECK_STR(udeg(5), "0.000005");
  CHECK_STR(udeg(-5), "-0.000005");
  CHECK_STR(udeg(0), "0.000000");
  CHECK_STR(udeg(-180000000), "-180.000000");

  // never writes past the buffer
  char small[4];
  format_fixed(123.45f, 2, small, sizeof(small));
  CHECK(std::strlen(small) < sizeof(small));
}

static void test_t_line() {
  char buf[kMaxOutLine];
  SensorReadings s = good_sensors();
  CHECK(build_t_line(s, 12.1f, buf, sizeof(buf)));
  CHECK_STR(buf, "T 39.091230 -77.153400 212.5 1 9 12.10 21.4 7.60 12.0 410\n");

  // missing sensors and no fix -> nan in those slots, still 11 fields
  s.gps_fix = false;
  s.sats = 0;
  s.heading_deg = NAN;
  s.temp_c = s.ph = s.turb_ntu = s.cond_us = NAN;
  CHECK(build_t_line(s, NAN, buf, sizeof(buf)));
  CHECK_STR(buf, "T nan nan nan 0 0 nan nan nan nan nan\n");

  // too small a buffer -> refuses rather than sending half a line
  char tiny[20];
  CHECK(!build_t_line(good_sensors(), 12.1f, tiny, sizeof(tiny)));

  CHECK(build_e_line("STOP_NO_PI", buf, sizeof(buf)));
  CHECK_STR(buf, "E STOP_NO_PI\n");
}

// ---- watchdog -----------------------------------------------------------------------

static void test_watchdog() {
  Watchdog w;
  CHECK(w.expired(0));  // nothing heard yet = stopped
  w.feed(1000);
  CHECK(!w.expired(1000));
  CHECK(!w.expired(2999));
  CHECK(w.expired(3000));  // exactly 2000 ms
  CHECK(w.expired(3001));
  w.feed(5000);
  CHECK(!w.expired(5001));

  // millis() rollover: fed just before the wrap, checked just after
  Watchdog r;
  r.feed(0xFFFFFF00u);           // 256 ms before the wrap
  CHECK(!r.expired(0xFFFFFFFFu));
  CHECK(!r.expired(100));        // 356 ms after feeding, after the wrap
  CHECK(!r.expired(1743));       // 1999 ms
  CHECK(r.expired(1744));        // 2000 ms

  // once expired, a further wrap of the counter can't make it look fresh
  Watchdog s;
  s.feed(0);
  CHECK(s.expired(5000));
  CHECK(s.expired(0xFFFFFFFFu));
  CHECK(s.expired(1));
}

// ---- battery ---------------------------------------------------------------------------

static void test_battery() {
  CHECK(std::fabs(battery_percent(12.6f) - 100.0f) < 0.01f);
  CHECK(std::fabs(battery_percent(10.5f) - 0.0f) < 0.01f);
  CHECK(std::fabs(battery_percent(11.55f) - 50.0f) < 0.01f);
  CHECK(battery_percent(14.0f) == 100.0f);
  CHECK(battery_percent(9.0f) == 0.0f);
  CHECK(std::fabs(adc_to_volts(645, 1023, 5.0f, 4.0f) - 12.61f) < 0.01f);

  // averaging: one dip doesn't move the average much
  Battery b;
  CHECK(!b.has_reading());
  CHECK(std::isnan(b.average_volts()));
  uint32_t t = 0;
  for (int i = 0; i < 20; i++, t += 250) b.update(t, 12.0f);
  b.update(t, 10.0f);  // one surge sample
  t += 250;
  CHECK(b.average_volts() > 11.8f);
  CHECK(!b.take_warning());
  // samples closer than 250 ms are skipped
  Battery c;
  c.update(0, 12.0f);
  c.update(100, 10.0f);
  CHECK(std::fabs(c.average_volts() - 12.0f) < 1e-4f);
  // NaN readings are ignored
  c.update(300, NAN);
  CHECK(std::fabs(c.average_volts() - 12.0f) < 1e-4f);

  // walk the voltage down slowly: each threshold fires exactly once
  Battery w;
  int warnings = 0;
  bool cut_seen_above_10 = false;
  t = 0;
  for (float v = 12.6f; v > 10.4f; v -= 0.002f, t += 250) {
    w.update(t, v);
    while (w.take_warning()) warnings++;
    if (w.motors_cut() && w.percent() > 10.0f) cut_seen_above_10 = true;
  }
  CHECK(warnings == 3);
  CHECK(w.motors_cut());
  CHECK(!cut_seen_above_10);
  // the cut stays on even if the voltage bounces back
  for (int i = 0; i < 40; i++, t += 250) w.update(t, 12.0f);
  CHECK(w.motors_cut());
  CHECK(!w.take_warning());

  // starting already low: all three warnings at once
  Battery low;
  low.update(0, 10.6f);
  int n = 0;
  while (low.take_warning()) n++;
  CHECK(n == 3);
  CHECK(low.motors_cut());
}

// ---- motors ------------------------------------------------------------------------------

static void test_motors() {
  MotorDrive d = motor_to_drive(0.5f);
  CHECK(d.forward && d.pwm == 128);
  d = motor_to_drive(-1.0f);
  CHECK(!d.forward && d.pwm == 255);
  d = motor_to_drive(0.0f);
  CHECK(d.pwm == 0);
  d = motor_to_drive(3.0f);
  CHECK(d.forward && d.pwm == 255);
  d = motor_to_drive(NAN);
  CHECK(d.pwm == 0);
}

// ---- the whole core ---------------------------------------------------------------------

static void test_core_drive_and_watchdog() {
  FakeHal hal;
  BoatCore core(hal);
  SensorReadings s = good_sensors();

  core.step(0, s);
  CHECK(hal.left == 0.0f && hal.right == 0.0f && !hal.conveyor);  // off until told
  CHECK(hal.count("E STOP_NO_PI\n") == 0);  // no event before the Pi ever spoke
  CHECK(hal.lines.size() == 1 && hal.lines[0][0] == 'T');  // first T right away

  send(core, "M 0.45 0.75 1\n", 100);
  core.step(100, s);
  CHECK(std::fabs(hal.left - 0.45f) < 1e-6f && std::fabs(hal.right - 0.75f) < 1e-6f && hal.conveyor);

  // keep sending every 100 ms up to t=1000, then go quiet
  for (uint32_t t = 200; t <= 1000; t += 100) {
    send(core, "M 0.45 0.75 1\n", t);
    core.step(t, s);
  }
  core.step(2999, s);
  CHECK(hal.left != 0.0f);  // 1999 ms of silence: still running
  core.step(3000, s);
  CHECK(hal.left == 0.0f && hal.right == 0.0f && !hal.conveyor);  // 2000 ms: stop
  CHECK(hal.count("E STOP_NO_PI\n") == 1);
  for (uint32_t t = 3050; t < 9000; t += 50) core.step(t, s);
  CHECK(hal.count("E STOP_NO_PI\n") == 1);  // only once per silence
  CHECK(hal.left == 0.0f);

  // a valid M line brings it back and re-arms the event
  send(core, "M 0.2 0.2 0\n", 9000);
  core.step(9000, s);
  CHECK(std::fabs(hal.left - 0.2f) < 1e-6f);
  core.step(11000, s);
  CHECK(hal.left == 0.0f);
  CHECK(hal.count("E STOP_NO_PI\n") == 2);
}

static void test_core_malformed_does_not_feed_watchdog() {
  FakeHal hal;
  BoatCore core(hal);
  SensorReadings s = good_sensors();
  send(core, "M 0.5 0.5 0\n", 0);
  core.step(0, s);
  CHECK(hal.left == 0.5f);
  // garbage and almost-right lines keep arriving, but no valid M line
  for (uint32_t t = 100; t <= 2500; t += 100) {
    send(core, "M 0.5 0.5\n", t);
    send(core, "M 2 0 0\n", t);
    send(core, "hello\n", t);
    core.step(t, s);
  }
  CHECK(hal.left == 0.0f);
  CHECK(hal.count("E STOP_NO_PI\n") == 1);
  CHECK(core.command().left == 0.0f);
}

static void test_core_overlong_line() {
  FakeHal hal;
  BoatCore core(hal);
  SensorReadings s = good_sensors();
  // a valid command buried at the start of an overlong line must not count
  send(core, "M 0.9 0.9 1" + std::string(100, ' ') + "\n", 0);
  core.step(0, s);
  CHECK(hal.left == 0.0f);
  // and the next normal line works
  send(core, "M 0.3 0.3 0\n", 10);
  core.step(10, s);
  CHECK(std::fabs(hal.left - 0.3f) < 1e-6f);
  // split across several reads, like a real serial port
  send(core, "M 0.", 20);
  send(core, "6 0.6", 21);
  send(core, " 1\n", 22);
  core.step(22, s);
  CHECK(std::fabs(hal.left - 0.6f) < 1e-6f && hal.conveyor);
}

static void test_core_watchdog_rollover() {
  FakeHal hal;
  BoatCore core(hal);
  SensorReadings s = good_sensors();
  uint32_t t = 0xFFFFFC00u;  // ~1 s before millis() wraps
  for (int i = 0; i < 30; i++, t += 100) {  // crosses the wrap while commanded
    send(core, "M 0.4 0.4 0\n", t);
    core.step(t, s);
    CHECK(hal.left == 0.4f);
  }
  CHECK(hal.count("E STOP_NO_PI\n") == 0);
  uint32_t last = t - 100;
  core.step(last + 1999, s);
  CHECK(hal.left == 0.4f);
  core.step(last + 2000, s);
  CHECK(hal.left == 0.0f);
  CHECK(hal.count("E STOP_NO_PI\n") == 1);
}

static void test_core_battery() {
  FakeHal hal;
  BoatCore core(hal);
  uint32_t t = 0;
  int batt_low = 0;
  // drive the whole time while the battery runs down from 12.6 V to 10.4 V
  for (float v = 12.6f; v > 10.4f; v -= 0.002f, t += 100) {
    send(core, "M 1 1 1\n", t);
    core.step(t, good_sensors(v));
    if (core.battery().percent() > 10.5f) CHECK(hal.left == 1.0f);
  }
  for (const auto& l : hal.lines) batt_low += (l == "E BATT_LOW\n");
  CHECK(batt_low == 3);
  // the Pi is still commanding full power, but the Arduino says no
  send(core, "M 1 1 1\n", t);
  core.step(t, good_sensors(10.4f));
  CHECK(hal.left == 0.0f && hal.right == 0.0f && !hal.conveyor);
  CHECK(hal.count("E STOP_NO_PI\n") == 0);  // that's a battery stop, not a Pi stop
}

static void test_core_gps_lost_and_telemetry_rate() {
  FakeHal hal;
  BoatCore core(hal);
  SensorReadings s = good_sensors();
  for (uint32_t t = 0; t < 5000; t += 50) core.step(t, s);
  int t_lines = 0;
  for (const auto& l : hal.lines) t_lines += (l[0] == 'T');
  CHECK(t_lines == 25);  // 5 Hz: at 0, 200, 400, ... 4800
  // and evenly spaced: no two T lines in the same 200 ms
  {
    FakeHal h2;
    BoatCore c2(h2);
    int in_first_190 = 0;
    for (uint32_t t = 0; t < 190; t += 10) c2.step(t, s);
    for (const auto& l : h2.lines) in_first_190 += (l[0] == 'T');
    CHECK(in_first_190 == 1);
  }

  s.gps_fix = false;
  core.step(5000, s);
  core.step(5050, s);
  CHECK(hal.count("E GPS_LOST\n") == 1);
  s.gps_fix = true;
  core.step(5100, s);
  s.gps_fix = false;
  core.step(5150, s);
  CHECK(hal.count("E GPS_LOST\n") == 2);

  // every T line has exactly 11 fields, as boat-pi/arduino.py requires
  for (const auto& l : hal.lines) {
    if (l[0] != 'T') continue;
    int fields = 0;
    bool in_tok = false;
    for (char c : l) {
      bool sp = (c == ' ' || c == '\n');
      if (!sp && !in_tok) fields++;
      in_tok = !sp;
    }
    CHECK(fields == 11);
    CHECK(l.back() == '\n');
  }
}

int main() {
  test_m_parse();
  test_line_reader();
  test_format();
  test_t_line();
  test_watchdog();
  test_battery();
  test_motors();
  test_core_drive_and_watchdog();
  test_core_malformed_does_not_feed_watchdog();
  test_core_overlong_line();
  test_core_watchdog_rollover();
  test_core_battery();
  test_core_gps_lost_and_telemetry_rate();
  std::printf("%d passed, %d failed\n", g_passed, g_failed);
  return g_failed == 0 ? 0 : 1;
}
