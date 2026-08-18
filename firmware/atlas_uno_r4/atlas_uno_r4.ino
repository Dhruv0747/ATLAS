#include <Arduino.h>
#include <Wire.h>
#include <Arduino_LED_Matrix.h>
#include <Adafruit_BME680.h>
#include <Adafruit_AMG88xx.h>
#include <Adafruit_BNO08x.h>

// Project ATLAS - Arduino UNO R4 WiFi sensor/servo/GNSS firmware.
// USB Serial: Jetson command and telemetry link at 115200 baud.
// Serial1 D0/RX, D1/TX: Waveshare L76K at 9600 baud.

constexpr uint8_t FRONT_TRIG = 2;
constexpr uint8_t FRONT_ECHO = 3;
constexpr uint8_t LEFT_TRIG = 4;
constexpr uint8_t LEFT_ECHO = 5;
constexpr uint8_t RIGHT_TRIG = 6;
constexpr uint8_t RIGHT_ECHO = 7;

constexpr uint8_t PCA9685_ADDR = 0x40;
constexpr uint8_t BME680_ADDRS[] = {0x77, 0x76};
constexpr uint8_t AMG8833_ADDRS[] = {0x69, 0x68};
constexpr uint8_t BNO08X_ADDRS[] = {0x4B, 0x4A};
constexpr uint32_t USB_BAUD = 115200;
constexpr uint32_t GPS_BAUD = 9600;
// ATLAS uses a multi-device rover harness rather than a short PCB trace.
// 50 kHz gives the bus more settling margin without reducing sensor utility.
constexpr uint32_t I2C_CLOCK_HZ = 50000;
constexpr uint32_t I2C_POWER_UP_DELAY_MS = 1200;
constexpr uint32_t ECHO_TIMEOUT_US = 24000;  // About 4.1 m maximum.
const uint32_t GPS_BAUDS[] = {9600, 115200, 38400, 57600, 4800};
constexpr size_t GPS_BAUD_COUNT = sizeof(GPS_BAUDS) / sizeof(GPS_BAUDS[0]);

ArduinoLEDMatrix matrix;
TwoWire *sensor_wire = &Wire;
Adafruit_BME680 *bme680 = nullptr;
Adafruit_AMG88xx amg8833;
Adafruit_BNO08x bno08x(-1);
sh2_SensorValue_t bno_value;

bool bme_online = false;
bool amg_online = false;
bool bno_online = false;
uint8_t bme_addr = 0;
uint8_t amg_addr = 0;
uint8_t bno_addr = 0;
float bno_qx = 0.0f, bno_qy = 0.0f, bno_qz = 0.0f, bno_qw = 1.0f;
float bno_gx = 0.0f, bno_gy = 0.0f, bno_gz = 0.0f;
float bno_ax = 0.0f, bno_ay = 0.0f, bno_az = 0.0f;
float bno_mx = 0.0f, bno_my = 0.0f, bno_mz = 0.0f;
bool bno_have_q = false, bno_have_g = false, bno_have_a = false, bno_have_m = false;

int distances_mm[3] = {-1, -1, -1};
const uint8_t trig_pins[3] = {FRONT_TRIG, LEFT_TRIG, RIGHT_TRIG};
const uint8_t echo_pins[3] = {FRONT_ECHO, LEFT_ECHO, RIGHT_ECHO};
uint8_t next_sensor = 0;

int servo_us[4] = {2000, 1500, 1500, 700};
bool pca_online = false;

char command_buffer[96];
size_t command_length = 0;
char gps_buffer[128];
size_t gps_length = 0;

uint32_t last_range_ms = 0;
uint32_t last_report_ms = 0;
uint32_t last_matrix_ms = 0;
uint32_t last_gps_status_ms = 0;
uint32_t last_gps_baud_switch_ms = 0;
uint32_t last_bme_ms = 0;
uint32_t last_amg_ms = 0;
uint32_t last_bno_report_ms = 0;
uint32_t last_i2c_retry_ms = 0;
uint32_t last_i2c_status_ms = 0;
uint32_t gps_bytes_at_baud = 0;
uint32_t gps_lines_at_baud = 0;
size_t gps_baud_index = 0;
bool gps_baud_locked = false;

bool i2cProbeOn(TwoWire &bus, uint8_t address) {
  bus.beginTransmission(address);
  return bus.endTransmission() == 0;
}

bool i2cProbe(uint8_t address) {
  return i2cProbeOn(*sensor_wire, address);
}

uint8_t printI2cBusScan(TwoWire &bus, const char *name) {
  Serial.print("I2C,BUS="); Serial.print(name); Serial.print(",ADDRS=");
  bool first = true;
  uint8_t count = 0;
  for (uint8_t address = 1; address < 127; ++address) {
    if (i2cProbeOn(bus, address)) {
      if (!first) Serial.print(';');
      if (address < 16) Serial.print('0');
      Serial.print(address, HEX);
      first = false;
      ++count;
    }
  }
  Serial.println();
  return count;
}

void printI2cScan() {
  printI2cBusScan(Wire, "Wire");
  printI2cBusScan(Wire1, "Wire1");
}

uint8_t countAtlasDevices(TwoWire &bus) {
  const uint8_t addresses[] = {0x40, 0x4A, 0x4B, 0x68, 0x69, 0x76, 0x77};
  uint8_t count = 0;
  for (uint8_t address : addresses) if (i2cProbeOn(bus, address)) ++count;
  return count;
}

bool selectSensorBus(bool force = false) {
  const uint8_t wire_count = countAtlasDevices(Wire);
  const uint8_t wire1_count = countAtlasDevices(Wire1);
  TwoWire *selected = wire1_count > wire_count ? &Wire1 : &Wire;
  if (!force && selected == sensor_wire) return false;
  sensor_wire = selected;
  pca_online = false;
  bme_online = false;
  amg_online = false;
  bno_online = false;
  if (bme680 != nullptr) delete bme680;
  bme680 = new Adafruit_BME680(sensor_wire);
  Serial.print("I2CSELECT,BUS=");
  Serial.print(sensor_wire == &Wire1 ? "Wire1" : "Wire");
  Serial.print(",WIRE="); Serial.print(wire_count);
  Serial.print(",WIRE1="); Serial.println(wire1_count);
  return true;
}

bool initializeBme() {
  for (uint8_t address : BME680_ADDRS) {
    if (!i2cProbe(address)) continue;
    if (bme680 != nullptr && bme680->begin(address)) {
      bme_addr = address;
      bme_online = true;
      bme680->setTemperatureOversampling(BME680_OS_8X);
      bme680->setHumidityOversampling(BME680_OS_2X);
      bme680->setPressureOversampling(BME680_OS_4X);
      bme680->setIIRFilterSize(BME680_FILTER_SIZE_3);
      bme680->setGasHeater(320, 150);
      return true;
    }
  }
  bme_online = false;
  bme_addr = 0;
  return false;
}

bool initializeAmg() {
  for (uint8_t address : AMG8833_ADDRS) {
    if (!i2cProbe(address)) continue;
    if (amg8833.begin(address, sensor_wire)) {
      amg_addr = address;
      amg_online = true;
      return true;
    }
  }
  amg_online = false;
  amg_addr = 0;
  return false;
}

void enableBnoReports() {
  bno08x.enableReport(SH2_ROTATION_VECTOR, 20000);
  bno08x.enableReport(SH2_GYROSCOPE_CALIBRATED, 20000);
  bno08x.enableReport(SH2_ACCELEROMETER, 20000);
  bno08x.enableReport(SH2_MAGNETIC_FIELD_CALIBRATED, 50000);
}

bool initializeBno() {
  for (uint8_t address : BNO08X_ADDRS) {
    if (!i2cProbe(address)) continue;
    if (bno08x.begin_I2C(address, sensor_wire)) {
      bno_addr = address;
      bno_online = true;
      enableBnoReports();
      return true;
    }
  }
  bno_online = false;
  bno_addr = 0;
  return false;
}

void initializeI2cSensors() {
  initializeBme();
  initializeAmg();
  initializeBno();
  Serial.print("I2CSTAT,PCA="); Serial.print(pca_online ? 1 : 0);
  Serial.print(",BME="); Serial.print(bme_online ? 1 : 0);
  Serial.print(",AMG="); Serial.print(amg_online ? 1 : 0);
  Serial.print(",BNO="); Serial.println(bno_online ? 1 : 0);
}

bool i2cWrite8(uint8_t reg, uint8_t value) {
  sensor_wire->beginTransmission(PCA9685_ADDR);
  sensor_wire->write(reg);
  sensor_wire->write(value);
  return sensor_wire->endTransmission() == 0;
}

bool pcaProbe() {
  sensor_wire->beginTransmission(PCA9685_ADDR);
  return sensor_wire->endTransmission() == 0;
}

void pcaInitialize() {
  pca_online = pcaProbe();
  if (!pca_online) return;

  // Sleep, configure 50 Hz, then restart with auto-increment enabled.
  i2cWrite8(0x00, 0x10);
  i2cWrite8(0xFE, 121);
  i2cWrite8(0x00, 0x20);
  delay(1);
  i2cWrite8(0x00, 0xA1);
}

bool pcaSetTicks(uint8_t channel, uint16_t on_tick, uint16_t off_tick) {
  if (!pca_online || channel > 15) return false;
  const uint8_t base = 0x06 + 4 * channel;
  sensor_wire->beginTransmission(PCA9685_ADDR);
  sensor_wire->write(base);
  sensor_wire->write(on_tick & 0xFF);
  sensor_wire->write((on_tick >> 8) & 0x0F);
  sensor_wire->write(off_tick & 0xFF);
  sensor_wire->write((off_tick >> 8) & 0x0F);
  if (sensor_wire->endTransmission() != 0) {
    pca_online = false;
    return false;
  }
  return true;
}

void setServo(uint8_t channel, int pulse_us) {
  if (channel > 3) return;
  pulse_us = constrain(pulse_us, 500, 2500);
  servo_us[channel] = pulse_us;
  const uint16_t ticks = (uint32_t)pulse_us * 4096UL / 20000UL;
  pcaSetTicks(channel, 0, ticks);
}

void freeServo(uint8_t channel) {
  if (channel > 15 || !pca_online) return;
  const uint8_t base = 0x06 + 4 * channel;
  sensor_wire->beginTransmission(PCA9685_ADDR);
  sensor_wire->write(base);
  sensor_wire->write(0);
  sensor_wire->write(0);
  sensor_wire->write(0);
  sensor_wire->write(0x10);  // Full OFF.
  sensor_wire->endTransmission();
}

void homeServos() {
  setServo(0, 2000);  // Left ultrasonic scan servo.
  setServo(1, 1500);  // Legacy camera bottom channel.
  setServo(2, 1500);  // Legacy camera upper channel.
  setServo(3, 700);   // Right ultrasonic scan servo.
}

int readRangeMm(uint8_t trig, uint8_t echo) {
  digitalWrite(trig, LOW);
  delayMicroseconds(3);
  digitalWrite(trig, HIGH);
  delayMicroseconds(10);
  digitalWrite(trig, LOW);
  const unsigned long duration = pulseIn(echo, HIGH, ECHO_TIMEOUT_US);
  if (duration == 0) return -1;
  const long mm = (long)(duration * 0.343f / 2.0f);
  return (mm >= 20 && mm <= 4200) ? (int)mm : -1;
}

void printTelemetry() {
  Serial.print("F=");
  Serial.print(distances_mm[0]);
  Serial.print(",L=");
  Serial.print(distances_mm[1]);
  Serial.print(",R=");
  Serial.print(distances_mm[2]);
  Serial.print(",LA=");
  Serial.print(servo_us[0]);
  Serial.print(",RA=");
  Serial.print(servo_us[3]);
  Serial.print(",C1=");
  Serial.print(servo_us[1]);
  Serial.print(",C2=");
  Serial.print(servo_us[2]);
  Serial.print(",PCA=");
  Serial.print(pca_online ? 1 : 0);
  Serial.println(",OK=1");
}

void processCommand(char *line) {
  if (strcmp(line, "SCAN") == 0) {
    printI2cScan();
    Serial.println("ACK,SCAN");
    return;
  }
  if (strcmp(line, "PCA?") == 0) {
    if (!pca_online) pcaInitialize();
    Serial.print("ACK,PCA,");
    Serial.println(pca_online ? 1 : 0);
    return;
  }
  if (strcmp(line, "HOME") == 0) {
    homeServos();
    Serial.println("ACK,HOME");
    return;
  }

  int channel = -1;
  int pulse = -1;
  if (sscanf(line, "SERVO,%d,%d", &channel, &pulse) == 2 && channel >= 0 && channel <= 15) {
    if (channel <= 3) setServo((uint8_t)channel, pulse);
    else {
      pulse = constrain(pulse, 500, 2500);
      const uint16_t ticks = (uint32_t)pulse * 4096UL / 20000UL;
      pcaSetTicks((uint8_t)channel, 0, ticks);
    }
    Serial.print("ACK,SERVO,");
    Serial.print(channel);
    Serial.print(',');
    Serial.println(pulse);
    return;
  }
  if (sscanf(line, "FREE,%d", &channel) == 1 && channel >= 0 && channel <= 15) {
    freeServo((uint8_t)channel);
    Serial.print("ACK,FREE,");
    Serial.println(channel);
    return;
  }
  Serial.print("ERR,UNKNOWN,");
  Serial.println(line);
}

void serviceBme(uint32_t now) {
  if (!bme_online || now - last_bme_ms < 1000) return;
  last_bme_ms = now;
  if (bme680 == nullptr || !bme680->performReading()) {
    bme_online = false;
    Serial.println("BME,OK=0");
    return;
  }
  Serial.print("BME,A="); Serial.print(bme_addr, HEX);
  Serial.print(",T="); Serial.print(bme680->temperature, 2);
  Serial.print(",H="); Serial.print(bme680->humidity, 2);
  Serial.print(",P="); Serial.print(bme680->pressure / 100.0f, 2);
  Serial.print(",G="); Serial.print(bme680->gas_resistance, 0);
  Serial.println(",OK=1");
}

void serviceAmg(uint32_t now) {
  if (!amg_online || now - last_amg_ms < 500) return;
  last_amg_ms = now;
  float pixels[AMG88xx_PIXEL_ARRAY_SIZE];
  amg8833.readPixels(pixels);
  float minimum = pixels[0], maximum = pixels[0], total = 0.0f;
  for (uint8_t i = 0; i < AMG88xx_PIXEL_ARRAY_SIZE; ++i) {
    minimum = min(minimum, pixels[i]);
    maximum = max(maximum, pixels[i]);
    total += pixels[i];
  }
  const float center = (pixels[27] + pixels[28] + pixels[35] + pixels[36]) / 4.0f;
  Serial.print("AMG,A="); Serial.print(amg_addr, HEX);
  Serial.print(",MIN="); Serial.print(minimum, 2);
  Serial.print(",MAX="); Serial.print(maximum, 2);
  Serial.print(",AVG="); Serial.print(total / AMG88xx_PIXEL_ARRAY_SIZE, 2);
  Serial.print(",CENTER="); Serial.print(center, 2);
  Serial.print(",PX=");
  for (uint8_t i = 0; i < AMG88xx_PIXEL_ARRAY_SIZE; ++i) {
    if (i) Serial.print(';');
    Serial.print(pixels[i], 2);
  }
  Serial.println(",OK=1");
}

void serviceBno(uint32_t now) {
  if (!bno_online) return;
  if (bno08x.wasReset()) enableBnoReports();
  uint8_t handled = 0;
  while (handled < 12 && bno08x.getSensorEvent(&bno_value)) {
    ++handled;
    switch (bno_value.sensorId) {
      case SH2_ROTATION_VECTOR:
        bno_qw = bno_value.un.rotationVector.real;
        bno_qx = bno_value.un.rotationVector.i;
        bno_qy = bno_value.un.rotationVector.j;
        bno_qz = bno_value.un.rotationVector.k;
        bno_have_q = true;
        break;
      case SH2_GYROSCOPE_CALIBRATED:
        bno_gx = bno_value.un.gyroscope.x;
        bno_gy = bno_value.un.gyroscope.y;
        bno_gz = bno_value.un.gyroscope.z;
        bno_have_g = true;
        break;
      case SH2_ACCELEROMETER:
        bno_ax = bno_value.un.accelerometer.x;
        bno_ay = bno_value.un.accelerometer.y;
        bno_az = bno_value.un.accelerometer.z;
        bno_have_a = true;
        break;
      case SH2_MAGNETIC_FIELD_CALIBRATED:
        bno_mx = bno_value.un.magneticField.x;
        bno_my = bno_value.un.magneticField.y;
        bno_mz = bno_value.un.magneticField.z;
        bno_have_m = true;
        break;
    }
  }
  if (now - last_bno_report_ms < 50 || !(bno_have_q && bno_have_g && bno_have_a)) return;
  last_bno_report_ms = now;
  Serial.print("BNO,A="); Serial.print(bno_addr, HEX);
  Serial.print(",QX="); Serial.print(bno_qx, 6);
  Serial.print(",QY="); Serial.print(bno_qy, 6);
  Serial.print(",QZ="); Serial.print(bno_qz, 6);
  Serial.print(",QW="); Serial.print(bno_qw, 6);
  Serial.print(",GX="); Serial.print(bno_gx, 5);
  Serial.print(",GY="); Serial.print(bno_gy, 5);
  Serial.print(",GZ="); Serial.print(bno_gz, 5);
  Serial.print(",AX="); Serial.print(bno_ax, 4);
  Serial.print(",AY="); Serial.print(bno_ay, 4);
  Serial.print(",AZ="); Serial.print(bno_az, 4);
  Serial.print(",MX="); Serial.print(bno_mx, 3);
  Serial.print(",MY="); Serial.print(bno_my, 3);
  Serial.print(",MZ="); Serial.print(bno_mz, 3);
  Serial.print(",MAG="); Serial.print(bno_have_m ? 1 : 0);
  Serial.println(",OK=1");
}

void retryOfflineI2cSensors(uint32_t now) {
  if (now - last_i2c_retry_ms < 10000) return;
  last_i2c_retry_ms = now;
  // Some breakouts power up after the UNO. Re-evaluate both UNO R4 buses
  // instead of permanently remaining on the empty bus selected at boot.
  if (selectSensorBus()) {
    pcaInitialize();
    initializeI2cSensors();
    return;
  }
  if (!pca_online) pcaInitialize();
  if (!bme_online) initializeBme();
  if (!amg_online) initializeAmg();
  if (!bno_online) initializeBno();
}

void reportI2cStatus(uint32_t now) {
  if (now - last_i2c_status_ms < 5000) return;
  last_i2c_status_ms = now;
  Serial.print("I2CSTAT,BUS="); Serial.print(sensor_wire == &Wire1 ? "Wire1" : "Wire");
  Serial.print(",WIRE="); Serial.print(countAtlasDevices(Wire));
  Serial.print(",WIRE1="); Serial.print(countAtlasDevices(Wire1));
  Serial.print(",SDA="); Serial.print(digitalRead(WIRE_SDA_PIN));
  Serial.print(",SCL="); Serial.print(digitalRead(WIRE_SCL_PIN));
  Serial.print(",SDA1="); Serial.print(digitalRead(WIRE1_SDA_PIN));
  Serial.print(",SCL1="); Serial.print(digitalRead(WIRE1_SCL_PIN));
  Serial.print(",PCA="); Serial.print(pca_online ? 1 : 0);
  Serial.print(",BME="); Serial.print(bme_online ? 1 : 0);
  Serial.print(",AMG="); Serial.print(amg_online ? 1 : 0);
  Serial.print(",BNO="); Serial.println(bno_online ? 1 : 0);
}

void serviceUsbCommands() {
  while (Serial.available()) {
    const char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      command_buffer[command_length] = '\0';
      if (command_length) processCommand(command_buffer);
      command_length = 0;
    } else if (command_length < sizeof(command_buffer) - 1) {
      command_buffer[command_length++] = c;
    } else {
      command_length = 0;
    }
  }
}

bool validNmeaLine(const char *line) {
  if (line == nullptr || line[0] != '$') return false;
  const char *asterisk = strchr(line, '*');
  if (asterisk == nullptr || strlen(asterisk) < 3) return false;
  uint8_t checksum = 0;
  for (const char *cursor = line + 1; cursor < asterisk; ++cursor) {
    const uint8_t value = (uint8_t)*cursor;
    if (value < 0x20 || value > 0x7E) return false;
    checksum ^= value;
  }
  char supplied[3] = {asterisk[1], asterisk[2], '\0'};
  char *end = nullptr;
  const long expected = strtol(supplied, &end, 16);
  return end == supplied + 2 && checksum == (uint8_t)expected;
}

void serviceGps() {
  while (Serial1.available()) {
    const char c = (char)Serial1.read();
    ++gps_bytes_at_baud;
    if (c == '\r') continue;
    if (c == '\n') {
      gps_buffer[gps_length] = '\0';
      if (gps_length > 6 && validNmeaLine(gps_buffer)) {
        ++gps_lines_at_baud;
        gps_baud_locked = true;
        Serial.print("GPS,");
        Serial.println(gps_buffer);
      }
      gps_length = 0;
    } else if (gps_length < sizeof(gps_buffer) - 1) {
      gps_buffer[gps_length++] = c;
    } else {
      gps_length = 0;
    }
  }
}

void serviceGpsDiagnostics(uint32_t now) {
  if (!gps_baud_locked && now - last_gps_baud_switch_ms >= 3000) {
    gps_baud_index = (gps_baud_index + 1) % GPS_BAUD_COUNT;
    Serial1.end();
    delay(2);
    Serial1.begin(GPS_BAUDS[gps_baud_index]);
    gps_bytes_at_baud = 0;
    gps_lines_at_baud = 0;
    gps_length = 0;
    last_gps_baud_switch_ms = now;
  }
  if (now - last_gps_status_ms >= 1000) {
    last_gps_status_ms = now;
    Serial.print("GPSSTAT,BAUD=");
    Serial.print(GPS_BAUDS[gps_baud_index]);
    Serial.print(",BYTES=");
    Serial.print(gps_bytes_at_baud);
    Serial.print(",LINES=");
    Serial.print(gps_lines_at_baud);
    Serial.print(",LOCK=");
    Serial.println(gps_baud_locked ? 1 : 0);
  }
}

void updateMatrix() {
  uint8_t frame[8][12] = {};
  // Front zone, left zone, right zone, and lower status bar.
  if (distances_mm[0] > 0 && distances_mm[0] < 600) {
    for (uint8_t r = 0; r < 3; ++r) for (uint8_t c = 4; c < 8; ++c) frame[r][c] = 1;
  }
  if (distances_mm[1] > 0 && distances_mm[1] < 500) {
    for (uint8_t r = 2; r < 6; ++r) for (uint8_t c = 0; c < 3; ++c) frame[r][c] = 1;
  }
  if (distances_mm[2] > 0 && distances_mm[2] < 500) {
    for (uint8_t r = 2; r < 6; ++r) for (uint8_t c = 9; c < 12; ++c) frame[r][c] = 1;
  }
  const int nearest = min(distances_mm[0] > 0 ? distances_mm[0] : 9999,
                          min(distances_mm[1] > 0 ? distances_mm[1] : 9999,
                              distances_mm[2] > 0 ? distances_mm[2] : 9999));
  const uint8_t width = nearest < 300 ? 12 : (nearest < 700 ? 8 : 4);
  for (uint8_t c = 0; c < width; ++c) frame[7][c] = 1;
  matrix.renderBitmap(frame, 8, 12);
}

void setup() {
  Serial.begin(USB_BAUD);
  Serial1.begin(GPS_BAUD);
  for (uint8_t i = 0; i < 3; ++i) {
    pinMode(trig_pins[i], OUTPUT);
    digitalWrite(trig_pins[i], LOW);
    pinMode(echo_pins[i], INPUT);
  }
  Wire.begin();
  Wire1.begin();
  Wire.setClock(I2C_CLOCK_HZ);
  Wire1.setClock(I2C_CLOCK_HZ);
  delay(I2C_POWER_UP_DELAY_MS);
  matrix.begin();
  selectSensorBus(true);
  pcaInitialize();
  if (pca_online) homeServos();
  printI2cScan();
  initializeI2cSensors();
  delay(100);
  Serial.println("ATLAS_UNO_SENSOR_HUB_V3");
}

void loop() {
  serviceUsbCommands();
  serviceGps();

  const uint32_t now = millis();
  serviceGpsDiagnostics(now);
  serviceBno(now);
  serviceBme(now);
  serviceAmg(now);
  retryOfflineI2cSensors(now);
  reportI2cStatus(now);
  if (now - last_range_ms >= 32) {
    last_range_ms = now;
    distances_mm[next_sensor] = readRangeMm(trig_pins[next_sensor], echo_pins[next_sensor]);
    next_sensor = (next_sensor + 1) % 3;
  }
  if (now - last_report_ms >= 120) {
    last_report_ms = now;
    printTelemetry();
  }
  if (now - last_matrix_ms >= 250) {
    last_matrix_ms = now;
    updateMatrix();
  }
}
