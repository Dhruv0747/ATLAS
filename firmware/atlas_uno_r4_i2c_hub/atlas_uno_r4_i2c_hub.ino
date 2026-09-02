#include <Arduino.h>
#include <Wire.h>
#include <Arduino_LED_Matrix.h>
#include <Adafruit_AMG88xx.h>
#include <Adafruit_BME680.h>
#include <Adafruit_BNO08x.h>

// Project ATLAS UNO R4 WiFi I2C sensor hub.
//
// Wiring (standard UNO header):
//   A4 / SDA -> sensor SDA
//   A5 / SCL -> sensor SCL
//   3V3      -> sensor logic power
//   GND      -> common ground
// The BNO08x is isolated on the UNO R4 Qwiic/Wire1 connector. Its unusual
// clock-stretching behavior must never be allowed to stop the main sensor bus.
//
// Commissioned devices:
//   0x40 PCA9685 camera pan/tilt controller
//   0x4B BNO08x IMU
//   0x69 AMG8833 8x8 thermal array
//   0x77 BME680 environmental sensor
//
// UART inputs:
//   D0 / RX  -> L76K TX (9600 baud, hardware Serial1)
//   D12 / RX -> RD-03D TX (256000 baud, independent hardware UART)
// Matching UART outputs are D1 / TX -> L76K RX and D11 / TX -> RD-03D RX.
// D13 cannot replace D11 because it belongs to a different SCI channel.
//
// USB CDC is the Jetson telemetry and command connection. The PCA9685 servo
// channels are released at startup so boot/reconnect cannot unexpectedly move
// the camera or create a servo-rail current surge.

constexpr uint32_t USB_BAUD = 115200;
constexpr uint32_t I2C_HZ = 100000;
constexpr uint32_t GPS_DEFAULT_BAUD = 9600;
constexpr uint32_t RADAR_DEFAULT_BAUD = 256000;
constexpr uint8_t RADAR_TX_PIN = 11;
constexpr uint8_t RADAR_RX_PIN = 12;
constexpr uint8_t ULTRASONIC_COUNT = 4;
constexpr uint8_t ULTRASONIC_TRIG_PINS[ULTRASONIC_COUNT] = {2, 4, 6, 8};
constexpr uint8_t ULTRASONIC_ECHO_PINS[ULTRASONIC_COUNT] = {3, 5, 7, 9};
constexpr uint32_t ULTRASONIC_TIMEOUT_US = 24000;
constexpr uint32_t ULTRASONIC_SAMPLE_MS = 45;
constexpr uint32_t ULTRASONIC_REPORT_MS = 250;
constexpr uint8_t BME_ADDRS[] = {0x77, 0x76};
constexpr uint8_t AMG_ADDRS[] = {0x69, 0x68};
constexpr uint8_t BNO_ADDRS[] = {0x4B, 0x4A};
constexpr uint8_t PCA9685_ADDR = 0x40;
constexpr uint8_t CAMERA_PAN_CHANNEL = 0;
constexpr uint8_t CAMERA_TILT_CHANNEL = 1;
constexpr int CAMERA_MIN_PULSE_US = 700;
constexpr int CAMERA_MAX_PULSE_US = 2300;
constexpr int CAMERA_PAN_HOME_US = 1300;
constexpr int CAMERA_TILT_HOME_US = 2100;
constexpr uint32_t SENSOR_RETRY_MS = 30000;
// The commissioned BNO08x is currently absent from the isolated Qwiic bus.
// Re-running begin_I2C() against a missing/faulty BNO08x can block the UNO R4
// after about 30 seconds and freeze every otherwise healthy telemetry stream.
// Probe it once at boot and only retry it through the explicit SCAN command.
constexpr bool BNO_PERIODIC_RETRY = false;

Adafruit_BME680 *bme = nullptr;
Adafruit_AMG88xx amg;
Adafruit_BNO08x bno(-1);
sh2_SensorValue_t bno_value;
UART radar_serial(RADAR_TX_PIN, RADAR_RX_PIN);
ArduinoLEDMatrix matrix;

bool bme_online = false;
bool amg_online = false;
bool bno_online = false;
bool pca_online = false;
uint8_t bme_addr = 0;
uint8_t amg_addr = 0;
uint8_t bno_addr = 0;
int camera_pan_us = CAMERA_PAN_HOME_US;
int camera_tilt_us = CAMERA_TILT_HOME_US;

float qx = 0, qy = 0, qz = 0, qw = 1;
float gx = 0, gy = 0, gz = 0;
float ax = 0, ay = 0, az = 0;
float mx = 0, my = 0, mz = 0;

uint32_t last_heartbeat_ms = 0;
uint32_t last_bme_ms = 0;
uint32_t last_amg_ms = 0;
uint32_t last_bno_ms = 0;
uint32_t last_status_ms = 0;
uint32_t last_retry_ms = 0;
uint32_t last_gps_byte_ms = 0;
uint32_t last_radar_byte_ms = 0;
uint32_t last_ultrasonic_sample_ms = 0;
uint32_t last_ultrasonic_report_ms = 0;
uint32_t last_matrix_ms = 0;
uint16_t i2c_recovery_count = 0;
uint32_t gps_bytes = 0;
uint32_t radar_bytes = 0;
uint32_t gps_baud = GPS_DEFAULT_BAUD;
uint32_t radar_baud = RADAR_DEFAULT_BAUD;
char command_buffer[128];
size_t command_length = 0;
char gps_buffer[160];
size_t gps_length = 0;
int ultrasonic_mm[ULTRASONIC_COUNT] = {-1, -1, -1, -1};
uint32_t ultrasonic_last_valid_ms[ULTRASONIC_COUNT] = {0, 0, 0, 0};
// ATLAS currently has only the rear sensor fitted. The remaining channels are
// commissioned in software but disabled until their hardware is installed.
bool ultrasonic_enabled[ULTRASONIC_COUNT] = {false, false, false, true};
uint8_t next_ultrasonic = 3;
uint8_t matrix_page = 0;

void configureSensorWire() {
  Wire.begin();
  Wire.setWireTimeout(25000, true);
  Wire.setClock(I2C_HZ);
}

void configureBnoWire() {
  Wire1.begin();
  Wire1.setWireTimeout(250000, false);
  Wire1.setClock(400000);
}

bool probeOn(TwoWire &bus, uint8_t address) {
  bus.beginTransmission(address);
  return bus.endTransmission() == 0;
}

bool probe(uint8_t address) {
  return probeOn(Wire, address);
}

bool recoverI2cBus() {
  Wire.end();
  pinMode(WIRE_SDA_PIN, INPUT_PULLUP);
  pinMode(WIRE_SCL_PIN, INPUT_PULLUP);
  delay(2);
  for (uint8_t pulse = 0; pulse < 18 && digitalRead(WIRE_SDA_PIN) == LOW; ++pulse) {
    pinMode(WIRE_SCL_PIN, OUTPUT);
    digitalWrite(WIRE_SCL_PIN, LOW);
    delayMicroseconds(8);
    pinMode(WIRE_SCL_PIN, INPUT_PULLUP);
    delayMicroseconds(8);
  }
  // Generate a STOP condition without ever driving either line high.
  pinMode(WIRE_SDA_PIN, OUTPUT);
  digitalWrite(WIRE_SDA_PIN, LOW);
  delayMicroseconds(8);
  pinMode(WIRE_SCL_PIN, INPUT_PULLUP);
  delayMicroseconds(8);
  pinMode(WIRE_SDA_PIN, INPUT_PULLUP);
  delayMicroseconds(8);
  const bool released = digitalRead(WIRE_SDA_PIN) == HIGH &&
                        digitalRead(WIRE_SCL_PIN) == HIGH;
  configureSensorWire();
  ++i2c_recovery_count;
  Serial.print("I2CRECOVERY,COUNT="); Serial.print(i2c_recovery_count);
  Serial.print(",RELEASED="); Serial.println(released ? 1 : 0);
  return released;
}

bool pcaWrite8(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(PCA9685_ADDR);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool pcaSetPulse(uint8_t channel, int pulse_us) {
  if (!pca_online || channel > 15) return false;
  pulse_us = constrain(pulse_us, CAMERA_MIN_PULSE_US, CAMERA_MAX_PULSE_US);
  const uint16_t ticks = static_cast<uint32_t>(pulse_us) * 4096UL / 20000UL;
  const uint8_t base = 0x06 + 4 * channel;
  Wire.beginTransmission(PCA9685_ADDR);
  Wire.write(base);
  Wire.write(0);
  Wire.write(0);
  Wire.write(ticks & 0xFF);
  Wire.write((ticks >> 8) & 0x0F);
  return Wire.endTransmission() == 0;
}

void pcaSetCamera(uint8_t channel, int pulse_us) {
  pulse_us = constrain(pulse_us, CAMERA_MIN_PULSE_US, CAMERA_MAX_PULSE_US);
  if (channel == CAMERA_PAN_CHANNEL) camera_pan_us = pulse_us;
  if (channel == CAMERA_TILT_CHANNEL) camera_tilt_us = pulse_us;
  pcaSetPulse(channel, pulse_us);
}

void pcaFree(uint8_t channel) {
  if (!pca_online || channel > 15) return;
  const uint8_t base = 0x06 + 4 * channel;
  Wire.beginTransmission(PCA9685_ADDR);
  Wire.write(base);
  Wire.write(0);
  Wire.write(0);
  Wire.write(0);
  Wire.write(0x10);
  Wire.endTransmission();
}

void initializePca() {
  pca_online = probe(PCA9685_ADDR);
  if (!pca_online) return;
  pca_online = pcaWrite8(0x00, 0x10) &&
               pcaWrite8(0xFE, 121) &&
               pcaWrite8(0x00, 0x20);
  delay(5);
  if (pca_online) {
    pcaFree(CAMERA_PAN_CHANNEL);
    pcaFree(CAMERA_TILT_CHANNEL);
  }
}

void scanBus() {
  Serial.print("I2C,BUS=UNO_R4_WIFI,ADDRS=");
  bool first = true;
  for (uint8_t address = 1; address < 127; ++address) {
    if (!probe(address)) continue;
    if (!first) Serial.print(';');
    if (address < 16) Serial.print('0');
    Serial.print(address, HEX);
    first = false;
  }
  Serial.println();
  Serial.print("I2C,BUS=UNO_R4_BNO_QWIIC,ADDRS=");
  first = true;
  for (uint8_t address = 1; address < 127; ++address) {
    if (!probeOn(Wire1, address)) continue;
    if (!first) Serial.print(';');
    if (address < 16) Serial.print('0');
    Serial.print(address, HEX);
    first = false;
  }
  Serial.println();
}

void enableBnoReports() {
  bno.enableReport(SH2_ROTATION_VECTOR, 20000);
  bno.enableReport(SH2_GYROSCOPE_CALIBRATED, 20000);
  bno.enableReport(SH2_ACCELEROMETER, 20000);
  bno.enableReport(SH2_MAGNETIC_FIELD_CALIBRATED, 50000);
}

void reportStatus() {
  Serial.print("I2CSTAT,HUB=UNO_R4_WIFI");
  Serial.print(",PCA="); Serial.print(pca_online ? 1 : 0);
  Serial.print(",BME="); Serial.print(bme_online ? 1 : 0);
  Serial.print(",AMG="); Serial.print(amg_online ? 1 : 0);
  Serial.print(",BNO="); Serial.print(bno_online ? 1 : 0);
  Serial.print(",NICLA_ENV=0,SDA="); Serial.print(digitalRead(SDA));
  Serial.print(",SCL="); Serial.print(digitalRead(SCL));
  Serial.print(",BNO_SDA="); Serial.print(digitalRead(WIRE1_SDA_PIN));
  Serial.print(",BNO_SCL="); Serial.println(digitalRead(WIRE1_SCL_PIN));
}

void initializeBno() {
  bno_online = false;
  for (uint8_t address : BNO_ADDRS) {
    if (probeOn(Wire1, address) && bno.begin_I2C(address, &Wire1)) {
      bno_addr = address;
      bno_online = true;
      enableBnoReports();
      break;
    }
  }
}

// Initialize only the main A4/A5 bus. The BNO08x lives on isolated Wire1 and
// must never be part of automatic recovery for these commissioned sensors.
void initializeMainSensors() {
  initializePca();

  bme_online = false;
  for (uint8_t address : BME_ADDRS) {
    if (!probe(address)) continue;
    if (bme == nullptr) bme = new Adafruit_BME680(&Wire);
    if (bme->begin(address)) {
      bme_addr = address;
      bme_online = true;
      bme->setTemperatureOversampling(BME680_OS_8X);
      bme->setHumidityOversampling(BME680_OS_2X);
      bme->setPressureOversampling(BME680_OS_4X);
      bme->setIIRFilterSize(BME680_FILTER_SIZE_3);
      bme->setGasHeater(320, 150);
      break;
    }
  }

  amg_online = false;
  for (uint8_t address : AMG_ADDRS) {
    if (probe(address) && amg.begin(address, &Wire)) {
      amg_addr = address;
      amg_online = true;
      break;
    }
  }

  reportStatus();
}

void reportBme() {
  if (!bme_online || bme == nullptr || !bme->performReading()) {
    Serial.println("BME,OK=0");
    bme_online = false;
    return;
  }
  Serial.print("BME,A="); Serial.print(bme_addr, HEX);
  Serial.print(",T="); Serial.print(bme->temperature, 2);
  Serial.print(",H="); Serial.print(bme->humidity, 2);
  Serial.print(",P="); Serial.print(bme->pressure / 100.0f, 2);
  Serial.print(",G="); Serial.print(static_cast<unsigned long>(bme->gas_resistance));
  Serial.println(",OK=1");
}

void reportAmg() {
  if (!amg_online) {
    Serial.println("AMG,OK=0");
    return;
  }
  float pixels[64];
  amg.readPixels(pixels);
  float minimum = pixels[0], maximum = pixels[0], total = 0;
  for (uint8_t i = 0; i < 64; ++i) {
    minimum = min(minimum, pixels[i]);
    maximum = max(maximum, pixels[i]);
    total += pixels[i];
  }
  const float center = (pixels[27] + pixels[28] + pixels[35] + pixels[36]) / 4.0f;
  Serial.print("AMG,A="); Serial.print(amg_addr, HEX);
  Serial.print(",PX=");
  for (uint8_t i = 0; i < 64; ++i) {
    if (i) Serial.print(';');
    Serial.print(pixels[i], 2);
  }
  Serial.print(",MIN="); Serial.print(minimum, 2);
  Serial.print(",MAX="); Serial.print(maximum, 2);
  Serial.print(",AVG="); Serial.print(total / 64.0f, 2);
  Serial.print(",CENTER="); Serial.print(center, 2);
  Serial.println(",OK=1");
}

void readBno() {
  if (!bno_online) return;
  if (bno.wasReset()) enableBnoReports();
  while (bno.getSensorEvent(&bno_value)) {
    switch (bno_value.sensorId) {
      case SH2_ROTATION_VECTOR:
        qx = bno_value.un.rotationVector.i;
        qy = bno_value.un.rotationVector.j;
        qz = bno_value.un.rotationVector.k;
        qw = bno_value.un.rotationVector.real;
        break;
      case SH2_GYROSCOPE_CALIBRATED:
        gx = bno_value.un.gyroscope.x;
        gy = bno_value.un.gyroscope.y;
        gz = bno_value.un.gyroscope.z;
        break;
      case SH2_ACCELEROMETER:
        ax = bno_value.un.accelerometer.x;
        ay = bno_value.un.accelerometer.y;
        az = bno_value.un.accelerometer.z;
        break;
      case SH2_MAGNETIC_FIELD_CALIBRATED:
        mx = bno_value.un.magneticField.x;
        my = bno_value.un.magneticField.y;
        mz = bno_value.un.magneticField.z;
        break;
    }
  }
}

void reportBno() {
  if (!bno_online) {
    Serial.println("BNO,OK=0");
    return;
  }
  Serial.print("BNO,A="); Serial.print(bno_addr, HEX);
  Serial.print(",QX="); Serial.print(qx, 6);
  Serial.print(",QY="); Serial.print(qy, 6);
  Serial.print(",QZ="); Serial.print(qz, 6);
  Serial.print(",QW="); Serial.print(qw, 6);
  Serial.print(",GX="); Serial.print(gx, 6);
  Serial.print(",GY="); Serial.print(gy, 6);
  Serial.print(",GZ="); Serial.print(gz, 6);
  Serial.print(",AX="); Serial.print(ax, 6);
  Serial.print(",AY="); Serial.print(ay, 6);
  Serial.print(",AZ="); Serial.print(az, 6);
  Serial.print(",MX="); Serial.print(mx, 6);
  Serial.print(",MY="); Serial.print(my, 6);
  Serial.print(",MZ="); Serial.print(mz, 6);
  Serial.println(",OK=1");
}

int readUltrasonicMm(uint8_t trig_pin, uint8_t echo_pin) {
  digitalWrite(trig_pin, LOW);
  delayMicroseconds(3);
  digitalWrite(trig_pin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trig_pin, LOW);
  const unsigned long duration = pulseIn(echo_pin, HIGH, ULTRASONIC_TIMEOUT_US);
  if (duration == 0) return -1;
  const long distance_mm = static_cast<long>(duration * 0.343f / 2.0f);
  return (distance_mm >= 20 && distance_mm <= 4200)
           ? static_cast<int>(distance_mm) : -1;
}

void sampleNextUltrasonic(uint32_t now) {
  for (uint8_t checked = 0; checked < ULTRASONIC_COUNT; ++checked) {
    next_ultrasonic = (next_ultrasonic + 1) % ULTRASONIC_COUNT;
    if (!ultrasonic_enabled[next_ultrasonic]) continue;
    ultrasonic_mm[next_ultrasonic] = readUltrasonicMm(
      ULTRASONIC_TRIG_PINS[next_ultrasonic],
      ULTRASONIC_ECHO_PINS[next_ultrasonic]);
    if (ultrasonic_mm[next_ultrasonic] > 0) {
      ultrasonic_last_valid_ms[next_ultrasonic] = now;
    }
    return;
  }
}

const char *ultrasonicState(uint8_t index, uint32_t now) {
  if (!ultrasonic_enabled[index]) return "DISABLED";
  if (ultrasonic_last_valid_ms[index] != 0 &&
      now - ultrasonic_last_valid_ms[index] < 30000) return "ONLINE";
  return "NO_ECHO";
}

void reportUltrasonics(uint32_t now) {
  Serial.print("F="); Serial.print(ultrasonic_mm[0]);
  Serial.print(",L="); Serial.print(ultrasonic_mm[1]);
  Serial.print(",R="); Serial.print(ultrasonic_mm[2]);
  Serial.print(",B="); Serial.print(ultrasonic_mm[3]);
  Serial.print(",LA=-1,RA=-1,C1="); Serial.print(camera_pan_us);
  Serial.print(",C2="); Serial.print(camera_tilt_us);
  Serial.print(",PCA="); Serial.print(pca_online ? 1 : 0);
  Serial.println(",OK=1");
  Serial.print("USTAT,F="); Serial.print(ultrasonicState(0, now));
  Serial.print(",L="); Serial.print(ultrasonicState(1, now));
  Serial.print(",R="); Serial.print(ultrasonicState(2, now));
  Serial.print(",B="); Serial.println(ultrasonicState(3, now));
}

void drawGlyph(uint8_t frame[8][12], const uint8_t glyph[7], uint8_t x) {
  for (uint8_t row = 0; row < 7; ++row) {
    for (uint8_t col = 0; col < 5; ++col) {
      if (glyph[row] & (1U << (4 - col))) frame[row][x + col] = 1;
    }
  }
}

const uint8_t GLYPH_P[7] = {30, 17, 17, 30, 16, 16, 16};
const uint8_t GLYPH_E[7] = {31, 16, 16, 30, 16, 16, 31};
const uint8_t GLYPH_T[7] = {31, 4, 4, 4, 4, 4, 4};
const uint8_t GLYPH_I[7] = {31, 4, 4, 4, 4, 4, 31};
const uint8_t GLYPH_G[7] = {14, 17, 16, 23, 17, 17, 14};
const uint8_t GLYPH_D[7] = {30, 17, 17, 17, 17, 17, 30};
const uint8_t GLYPH_F[7] = {31, 16, 16, 30, 16, 16, 16};
const uint8_t GLYPH_L[7] = {16, 16, 16, 16, 16, 16, 31};
const uint8_t GLYPH_R[7] = {30, 17, 17, 30, 20, 18, 17};
const uint8_t GLYPH_B[7] = {30, 17, 17, 30, 17, 17, 30};
const uint8_t GLYPH_OK[7] = {0, 1, 2, 20, 8, 0, 0};
const uint8_t GLYPH_X[7] = {17, 10, 4, 4, 10, 17, 0};
const uint8_t GLYPH_OFF[7] = {0, 0, 0, 31, 0, 0, 0};

void updateMatrix(uint32_t now) {
  const uint8_t *label = GLYPH_P;
  uint8_t state = 0;  // 0=offline, 1=healthy, 2=disabled
  switch (matrix_page) {
    case 0: label = GLYPH_P; state = pca_online; break;
    case 1: label = GLYPH_E; state = bme_online; break;
    case 2: label = GLYPH_T; state = amg_online; break;
    case 3: label = GLYPH_I; state = bno_online; break;
    case 4: label = GLYPH_G; state = (last_gps_byte_ms && now - last_gps_byte_ms < 3000); break;
    case 5: label = GLYPH_D; state = (last_radar_byte_ms && now - last_radar_byte_ms < 3000); break;
    case 6: label = GLYPH_F; state = ultrasonic_enabled[0] ?
      (ultrasonic_last_valid_ms[0] && now - ultrasonic_last_valid_ms[0] < 30000) : 2; break;
    case 7: label = GLYPH_L; state = ultrasonic_enabled[1] ?
      (ultrasonic_last_valid_ms[1] && now - ultrasonic_last_valid_ms[1] < 30000) : 2; break;
    case 8: label = GLYPH_R; state = ultrasonic_enabled[2] ?
      (ultrasonic_last_valid_ms[2] && now - ultrasonic_last_valid_ms[2] < 30000) : 2; break;
    case 9: label = GLYPH_B; state = ultrasonic_enabled[3] ?
      (ultrasonic_last_valid_ms[3] && now - ultrasonic_last_valid_ms[3] < 30000) : 2; break;
  }
  uint8_t frame[8][12] = {};
  drawGlyph(frame, label, 0);
  drawGlyph(frame, state == 1 ? GLYPH_OK : (state == 2 ? GLYPH_OFF : GLYPH_X), 7);
  matrix.renderBitmap(frame, 8, 12);
  matrix_page = (matrix_page + 1) % 10;
}

void forwardGps() {
  while (Serial1.available()) {
    const char c = static_cast<char>(Serial1.read());
    ++gps_bytes;
    last_gps_byte_ms = millis();
    if (c == '\r') continue;
    if (c == '\n') {
      if (gps_length && gps_buffer[0] == '$') {
        gps_buffer[gps_length] = '\0';
        Serial.print("GPS,"); Serial.println(gps_buffer);
      }
      gps_length = 0;
    } else if (gps_length < sizeof(gps_buffer) - 1) {
      gps_buffer[gps_length++] = c;
    } else {
      gps_length = 0;
    }
  }
}

void forwardRadar() {
  if (!radar_serial.available()) return;
  Serial.print("RADARHEX,");
  uint8_t count = 0;
  while (radar_serial.available() && count < 96) {
    const uint8_t value = static_cast<uint8_t>(radar_serial.read());
    if (value < 16) Serial.print('0');
    Serial.print(value, HEX);
    ++count;
    ++radar_bytes;
    last_radar_byte_ms = millis();
  }
  Serial.println();
}

void setGpsBaud(uint32_t baud) {
  if (baud < 1200 || baud > 115200) return;
  gps_baud = baud;
  Serial1.end();
  Serial1.begin(gps_baud);
  Serial.print("ACK,GPSBAUD="); Serial.println(gps_baud);
}

void setRadarBaud(uint32_t baud) {
  if (baud < 1200 || baud > 921600) return;
  radar_baud = baud;
  radar_serial.end();
  radar_serial.begin(radar_baud);
  Serial.print("ACK,RADARBAUD="); Serial.println(radar_baud);
}

void handleCommand(const char *command) {
  if (!strcmp(command, "PING")) {
    Serial.println("PONG,ATLAS_UNO_R4_WIFI_I2C_HUB");
  } else if (!strcmp(command, "ID")) {
    Serial.println("ATLAS_UNO_R4_WIFI_I2C_HUB,V=1,BOARD=UNO_R4_WIFI,BUS=A4_A5");
  } else if (!strcmp(command, "SCAN")) {
    scanBus();
    initializeMainSensors();
    // BNO initialization is deliberately manual because a faulty/absent
    // BNO08x can block its library call and stop all UNO telemetry.
    initializeBno();
    reportStatus();
  } else if (!strcmp(command, "PCA?")) {
    if (!pca_online) initializePca();
    Serial.print("ACK,PCA,"); Serial.println(pca_online ? 1 : 0);
  } else if (!strcmp(command, "HOME")) {
    if (!pca_online) initializePca();
    if (pca_online) {
      pcaSetCamera(CAMERA_PAN_CHANNEL, CAMERA_PAN_HOME_US);
      pcaSetCamera(CAMERA_TILT_CHANNEL, CAMERA_TILT_HOME_US);
    }
    Serial.print("ACK,HOME,PCA="); Serial.println(pca_online ? 1 : 0);
  } else if (!strncmp(command, "SERVO,", 6)) {
    int channel = -1, pulse = -1;
    if (sscanf(command, "SERVO,%d,%d", &channel, &pulse) == 2 &&
        channel >= 0 && channel <= 15) {
      if (!pca_online) initializePca();
      pulse = constrain(pulse, CAMERA_MIN_PULSE_US, CAMERA_MAX_PULSE_US);
      if (pca_online) pcaSetCamera(static_cast<uint8_t>(channel), pulse);
      Serial.print("ACK,SERVO,"); Serial.print(channel); Serial.print(',');
      Serial.print(pulse); Serial.print(",PCA="); Serial.println(pca_online ? 1 : 0);
    } else {
      Serial.println("ERR,BAD_SERVO_COMMAND");
    }
  } else if (!strncmp(command, "FREE,", 5)) {
    const int channel = atoi(command + 5);
    if (channel >= 0 && channel <= 15) pcaFree(static_cast<uint8_t>(channel));
    Serial.print("ACK,FREE,"); Serial.println(channel);
  } else if (!strncmp(command, "GPSBAUD,", 8)) {
    setGpsBaud(strtoul(command + 8, nullptr, 10));
  } else if (!strncmp(command, "RADARBAUD,", 10)) {
    setRadarBaud(strtoul(command + 10, nullptr, 10));
  } else if (!strncmp(command, "USENABLE,", 9)) {
    char name = 0;
    int enabled = 0;
    if (sscanf(command, "USENABLE,%c,%d", &name, &enabled) == 2) {
      int index = name == 'F' ? 0 : name == 'L' ? 1 :
                  name == 'R' ? 2 : name == 'B' ? 3 : -1;
      if (index >= 0) {
        ultrasonic_enabled[index] = enabled != 0;
        ultrasonic_mm[index] = -1;
        ultrasonic_last_valid_ms[index] = 0;
        Serial.print("ACK,USENABLE,"); Serial.print(name); Serial.print(',');
        Serial.println(ultrasonic_enabled[index] ? 1 : 0);
      } else {
        Serial.println("ERR,BAD_ULTRASONIC_NAME");
      }
    } else {
      Serial.println("ERR,BAD_USENABLE_COMMAND");
    }
  } else {
    Serial.print("ERR,UNKNOWN_COMMAND="); Serial.println(command);
  }
}

void readCommands() {
  while (Serial.available()) {
    const char c = static_cast<char>(Serial.read());
    if (c == '\r') continue;
    if (c == '\n') {
      command_buffer[command_length] = '\0';
      if (command_length) handleCommand(command_buffer);
      command_length = 0;
    } else if (command_length < sizeof(command_buffer) - 1) {
      command_buffer[command_length++] = c;
    } else {
      command_length = 0;
    }
  }
}

void setup() {
  Serial.begin(USB_BAUD);
  Serial1.begin(gps_baud);
  radar_serial.begin(radar_baud);
  for (uint8_t index = 0; index < ULTRASONIC_COUNT; ++index) {
    pinMode(ULTRASONIC_TRIG_PINS[index], OUTPUT);
    digitalWrite(ULTRASONIC_TRIG_PINS[index], LOW);
    pinMode(ULTRASONIC_ECHO_PINS[index], INPUT);
  }
  matrix.begin();
  configureSensorWire();
  configureBnoWire();
  delay(1200);
  Serial.println("ATLAS_UNO_R4_WIFI_I2C_HUB,V=1,BOARD=UNO_R4_WIFI,BUS=A4_A5");
  recoverI2cBus();
  scanBus();
  initializeMainSensors();
  // One boot-time BNO probe is safe; automatic main-bus recovery never
  // touches this isolated sensor again.
  initializeBno();
  reportStatus();
}

void loop() {
  const uint32_t now = millis();
  readCommands();
  forwardGps();
  forwardRadar();
  readBno();

  if (now - last_ultrasonic_sample_ms >= ULTRASONIC_SAMPLE_MS) {
    last_ultrasonic_sample_ms = now;
    sampleNextUltrasonic(now);
  }
  if (now - last_ultrasonic_report_ms >= ULTRASONIC_REPORT_MS) {
    last_ultrasonic_report_ms = now;
    reportUltrasonics(now);
  }
  if (now - last_matrix_ms >= 900) {
    last_matrix_ms = now;
    updateMatrix(now);
  }

  if (now - last_bme_ms >= 2000) {
    last_bme_ms = now;
    reportBme();
  }
  if (now - last_amg_ms >= 1000) {
    last_amg_ms = now;
    reportAmg();
  }
  if (now - last_bno_ms >= 100) {
    last_bno_ms = now;
    reportBno();
  }
  if (now - last_status_ms >= 5000) {
    last_status_ms = now;
    reportStatus();
  }
  if (now - last_retry_ms >= SENSOR_RETRY_MS) {
    last_retry_ms = now;
    if (!bme_online || !amg_online || !pca_online) {
      recoverI2cBus();
      initializeMainSensors();
    } else if (BNO_PERIODIC_RETRY && !bno_online) {
      Wire1.end();
      delay(5);
      configureBnoWire();
      initializeBno();
      reportStatus();
    }
  }
  if (now - last_heartbeat_ms >= 1000) {
    last_heartbeat_ms = now;
    Serial.print("HEARTBEAT,HUB=UNO_R4_WIFI,UP_MS="); Serial.print(now);
    Serial.print(",I2C_RECOVERIES="); Serial.print(i2c_recovery_count);
    Serial.print(",GPS_BAUD="); Serial.print(gps_baud);
    Serial.print(",GPS_BYTES="); Serial.print(gps_bytes);
    Serial.print(",RADAR_BAUD="); Serial.print(radar_baud);
    Serial.print(",RADAR_BYTES="); Serial.print(radar_bytes);
    Serial.print(",PCA="); Serial.print(pca_online ? 1 : 0);
    Serial.print(",BME="); Serial.print(bme_online ? 1 : 0);
    Serial.print(",AMG="); Serial.print(amg_online ? 1 : 0);
    Serial.print(",BNO="); Serial.println(bno_online ? 1 : 0);
  }
  delay(1);
}
