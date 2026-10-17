#include "telemetry.h"

#include "format.h"

bool build_t_line(const SensorReadings& s, float batt_avg_v, char* out, size_t cap) {
  LineBuilder b(out, cap);
  b.add("T ");
  // Without a fix the GPS position is stale or made up, so say "nan".
  if (s.gps_fix) {
    b.add_udeg(s.lat_udeg);
    b.add_char(' ');
    b.add_udeg(s.lon_udeg);
  } else {
    b.add("nan nan");
  }
  b.add_char(' ');
  b.add_fixed(s.heading_deg, 1);
  b.add(s.gps_fix ? " 1 " : " 0 ");
  b.add_uint(s.sats);
  b.add_char(' ');
  b.add_fixed(batt_avg_v, 2);
  b.add_char(' ');
  b.add_fixed(s.temp_c, 1);
  b.add_char(' ');
  b.add_fixed(s.ph, 2);
  b.add_char(' ');
  b.add_fixed(s.turb_ntu, 1);
  b.add_char(' ');
  b.add_fixed(s.cond_us, 0);
  b.add_char('\n');
  return !b.overflowed();
}

bool build_e_line(const char* code, char* out, size_t cap) {
  LineBuilder b(out, cap);
  b.add("E ");
  b.add(code);
  b.add_char('\n');
  return !b.overflowed();
}
