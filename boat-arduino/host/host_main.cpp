// The firmware, built for a laptop instead of the board, so the simulator runs
// the REAL Arduino logic (boat/src/) instead of a Python imitation of it.
//
// It implements the same BoatHal as boat.ino, but over stdin/stdout.
// sim/fake_arduino.py talks to it with this line protocol (one request at a
// time, so nothing can deadlock):
//
//   in:  rx <ms> <hex>
//        Bytes the Pi wrote to the serial port, as hex (so partial lines,
//        garbage and newlines all pass through untouched). The firmware's own
//        LineReader handles them. No reply.
//
//   in:  tick <ms> <lat> <lon> <heading> <fix> <sats> <batt_v> <temp> <ph> <turb> <cond>
//        Sensor readings as the HAL would read them on the boat. batt_v is
//        volts at the battery, i.e. AFTER the divider math (boat.ino does
//        that conversion with adc_to_volts(), which is unit-tested). Any value
//        may be "nan". Runs one firmware step, then replies:
//
//   out: tx <hex>                    zero or more: bytes the firmware wrote to serial
//   out: out <left> <right> <conv>   exactly one: the motor outputs it set
//
// <ms> plays the role of millis(): a 32-bit counter that wraps.
// This file is laptop-only, so it may use the standard library freely.

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "../boat/src/boat_core.h"

namespace {

class StdioHal : public BoatHal {
 public:
  void write_serial(const char* text) override {
    std::fputs("tx ", stdout);
    for (const char* p = text; *p != '\0'; p++) std::printf("%02x", (unsigned char)*p);
    std::fputc('\n', stdout);
  }

  void set_motors(float l, float r, bool c) override {
    left = l;
    right = r;
    conveyor = c;
  }

  float left = 0.0f;
  float right = 0.0f;
  bool conveyor = false;
};

uint32_t parse_ms(const std::string& s) {
  return (uint32_t)std::strtoull(s.c_str(), nullptr, 10);  // wraps like millis()
}

float parse_num(const std::string& s) {
  return std::strtof(s.c_str(), nullptr);  // understands "nan"
}

int hex_value(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

int32_t to_udeg(const std::string& text) {
  // Parse as double: a float would lose the 6th decimal.
  double d = std::strtod(text.c_str(), nullptr);
  if (std::isnan(d)) return 0;
  return (int32_t)std::llround(d * 1e6);
}

}  // namespace

int main() {
  StdioHal hal;
  BoatCore core(hal);

  std::string line;
  while (std::getline(std::cin, line)) {
    std::istringstream in(line);
    std::string cmd;
    in >> cmd;

    if (cmd == "rx") {
      std::string ms_text, hex;
      in >> ms_text >> hex;
      uint32_t ms = parse_ms(ms_text);
      for (size_t i = 0; i + 1 < hex.size(); i += 2) {
        int hi = hex_value(hex[i]), lo = hex_value(hex[i + 1]);
        if (hi < 0 || lo < 0) break;
        core.on_serial_byte((uint8_t)(hi * 16 + lo), ms);
      }
    } else if (cmd == "tick") {
      std::vector<std::string> f;
      std::string tok;
      while (in >> tok) f.push_back(tok);
      if (f.size() != 11) {
        std::fprintf(stderr, "boat-host: tick needs 11 fields, got %zu\n", f.size());
        return 2;
      }
      SensorReadings s;
      s.gps_fix = std::atoi(f[4].c_str()) != 0;
      s.lat_udeg = to_udeg(f[1]);
      s.lon_udeg = to_udeg(f[2]);
      s.sats = (uint8_t)std::atoi(f[5].c_str());
      s.heading_deg = parse_num(f[3]);
      s.batt_v = parse_num(f[6]);
      s.temp_c = parse_num(f[7]);
      s.ph = parse_num(f[8]);
      s.turb_ntu = parse_num(f[9]);
      s.cond_us = parse_num(f[10]);

      core.step(parse_ms(f[0]), s);
      std::printf("out %.4f %.4f %d\n", hal.left, hal.right, hal.conveyor ? 1 : 0);
      std::fflush(stdout);
    } else if (!cmd.empty()) {
      std::fprintf(stderr, "boat-host: unknown command %s\n", cmd.c_str());
    }
  }
  return 0;  // stdin closed: the simulator went away, so do we
}
