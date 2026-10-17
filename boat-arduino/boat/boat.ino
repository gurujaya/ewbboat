// Boat firmware: the thin, hardware-specific part.
//
// All the decisions (parsing M lines, the 2 s watchdog, battery rules, building
// T and E lines) live in src/ as plain C++ with no Arduino code, so the
// simulator on a laptop compiles and runs exactly the same logic.
// This file only does what needs real hardware:
//   - read the sensors into a SensorReadings
//   - put motor outputs on pins
//   - move bytes between Serial and the core
//
// Never use delay() in here: while the loop is stuck, M lines pile up and the
// watchdog can't act. Everything is timed with millis() inside BoatCore.

#include "src/battery.h"
#include "src/boat_core.h"
#include "src/motors.h"

// ---- Pins: PLACEHOLDERS until Electrical gives us the real list ------------
// (Uno: PWM works on pins 3, 5, 6, 9, 10, 11.)
const uint8_t PIN_LEFT_PWM = 5;    // PLACEHOLDER: left thruster speed
const uint8_t PIN_LEFT_DIR = 4;    // PLACEHOLDER: left thruster direction
const uint8_t PIN_RIGHT_PWM = 6;   // PLACEHOLDER: right thruster speed
const uint8_t PIN_RIGHT_DIR = 7;   // PLACEHOLDER: right thruster direction
const uint8_t PIN_CONVEYOR = 8;    // PLACEHOLDER: conveyor relay / driver enable
const uint8_t PIN_BATTERY = A0;    // PLACEHOLDER: battery divider midpoint

// ---- Battery divider: PLACEHOLDERS ------------------------------------------
// The pack is ~12.6 V but the pin can only take 5 V, so two resistors divide
// it down. DIVIDER_RATIO = (R_top + R_bottom) / R_bottom.
// Example: 30k on top, 10k on the bottom -> ratio 4.0, so 12.6 V reads 3.15 V.
const float DIVIDER_RATIO = 4.0f;  // PLACEHOLDER until Electrical picks resistors
const float ADC_VREF = 5.0f;       // Uno/Mega default reference. ESP32 would be 3.3.
const uint16_t ADC_MAX = 1023;     // 10-bit ADC on Uno/Mega

const unsigned long SERIAL_BAUD = 115200;  // docs/MESSAGES.md, "USB serial"

// ---- The hardware side of the HAL -------------------------------------------

class ArduinoHal : public BoatHal {
 public:
  void write_serial(const char* text) override {
    // If the 64-byte send buffer is full this waits a few ms; a T line is ~70
    // bytes, i.e. about 6 ms at 115200 baud, 5 times a second (~3 % of the
    // time, and only when the buffer is full). Acceptable.
    Serial.print(text);
  }

  void set_motors(float left, float right, bool conveyor) override {
    // PLACEHOLDER driver style: one direction pin + one PWM pin per motor.
    // Change this (and src/motors.cpp) when Electrical picks the driver.
    MotorDrive l = motor_to_drive(left);
    MotorDrive r = motor_to_drive(right);
    digitalWrite(PIN_LEFT_DIR, l.forward ? HIGH : LOW);
    analogWrite(PIN_LEFT_PWM, l.pwm);
    digitalWrite(PIN_RIGHT_DIR, r.forward ? HIGH : LOW);
    analogWrite(PIN_RIGHT_PWM, r.pwm);
    digitalWrite(PIN_CONVEYOR, conveyor ? HIGH : LOW);
  }
};

ArduinoHal hal;
BoatCore core(hal);

// ---- Sensors ------------------------------------------------------------------
// Each one fills its part of SensorReadings. Until the module is wired, it
// reports "no fix" / NaN, and the T line sends "nan" in that slot.

void read_gps(SensorReadings& s) {
  // TODO: GPS over UART with the TinyGPS++ library (feed it bytes from the GPS
  // serial port every loop; on an Uno that needs SoftwareSerial, on a Mega use
  // Serial1). Then: s.gps_fix = gps.location.isValid() && age < 2 s;
  // s.lat_udeg = lround(gps.location.lat() * 1e6) (better: rawLat()), etc.
  s.gps_fix = false;
  s.lat_udeg = 0;
  s.lon_udeg = 0;
  s.sats = 0;
}

void read_compass(SensorReadings& s) {
  // TODO: compass/IMU over I2C, library depends on the module Electrical picks
  // (for example Adafruit_LIS3MDL, QMC5883LCompass, or Adafruit_BNO055).
  // Add the local magnetic declination; result 0-360 clockwise from north.
  s.heading_deg = NAN;
}

void read_battery(SensorReadings& s) {
  // analogRead takes ~0.1 ms; fine every loop. BoatCore averages over 5 s.
  s.batt_v = adc_to_volts(analogRead(PIN_BATTERY), ADC_MAX, ADC_VREF, DIVIDER_RATIO);
}

void read_water(SensorReadings& s) {
  // TODO: temperature (likely DS18B20 with OneWire + DallasTemperature),
  // pH, turbidity and conductivity (analog boards, e.g. DFRobot Gravity).
  // Calibration constants and where they came from go in calibration.md.
  s.temp_c = NAN;
  s.ph = NAN;
  s.turb_ntu = NAN;
  s.cond_us = NAN;
}

// ---- setup / loop ---------------------------------------------------------------

void setup() {
  pinMode(PIN_LEFT_PWM, OUTPUT);
  pinMode(PIN_LEFT_DIR, OUTPUT);
  pinMode(PIN_RIGHT_PWM, OUTPUT);
  pinMode(PIN_RIGHT_DIR, OUTPUT);
  pinMode(PIN_CONVEYOR, OUTPUT);
  hal.set_motors(0.0f, 0.0f, false);  // everything off before anything else
  Serial.begin(SERIAL_BAUD);
}

void loop() {
  // 1. Hand every byte the Pi sent to the core. It finds whole lines itself.
  while (Serial.available() > 0) {
    core.on_serial_byte((uint8_t)Serial.read(), millis());
  }

  // 2. Read the sensors.
  SensorReadings s;
  read_gps(s);
  read_compass(s);
  read_battery(s);
  read_water(s);

  // 3. Let the core decide: motors, events, telemetry.
  core.step(millis(), s);
}
