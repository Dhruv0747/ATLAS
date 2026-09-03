#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_AMG88xx.h>
#include <Adafruit_BME680.h>
#include <Adafruit_BNO08x.h>
#include <Arduino_NiclaSenseEnv.h>

#define ATLAS_SENSOR_WIRE Wire2
#define ATLAS_GPS_SERIAL Serial2
#define ATLAS_RADAR_SERIAL Serial3
#define ATLAS_HUB_NAME "PORTENTA_H7"
#define ATLAS_BOARD_NAME "PORTENTA_H7_LITE"

// Project ATLAS Portenta H7 Lite sensor hub.
//
// Transport assignment on the Portenta Breakout:
//   USB CDC     -> Jetson telemetry/command link, 115200 baud
//   Wire2       -> external I2C sensor bus (J2-45 SDA, J2-47 SCL)
//   Serial2     -> GNSS (J2-26 TX, J2-28 RX), default 9600 baud
//   Serial3     -> RD-03D radar (J2-25 TX, J2-27 RX), default 256000 baud
//   D0-D7       -> four HC-SR04-compatible ultrasonic sensors
//
// Wire1 is intentionally never used: it is the Portenta internal PMIC/crypto bus.

constexpr uint32_t USB_BAUD = 115200;
constexpr uint32_t I2C_HZ = 100000;
constexpr uint32_t GPS_DEFAULT_BAUD = 9600;
constexpr uint32_t RADAR_DEFAULT_BAUD = 256000;
constexpr uint8_t NICLA_ENV_ADDR = 0x21;
constexpr uint8_t BME_ADDRS[] = {0x77, 0x76};
constexpr uint8_t AMG_ADDRS[] = {0x69, 0x68};
constexpr uint8_t BNO_ADDRS[] = {0x4B, 0x4A};
constexpr uint8_t ULTRASONIC_COUNT = 4;
constexpr uint8_t FRONT_TRIG = D0;
constexpr uint8_t FRONT_ECHO = D1;
constexpr uint8_t LEFT_TRIG = D2;
constexpr uint8_t LEFT_ECHO = D3;
constexpr uint8_t RIGHT_TRIG = D4;
constexpr uint8_t RIGHT_ECHO = D5;
constexpr uint8_t REAR_TRIG = D6;
constexpr uint8_t REAR_ECHO = D7;
constexpr uint32_t ULTRASONIC_ECHO_TIMEOUT_US = 24000;
constexpr uint32_t ULTRASONIC_SAMPLE_INTERVAL_MS = 40;
constexpr uint32_t ULTRASONIC_REPORT_INTERVAL_MS = 120;

Adafruit_BME680 *bme = nullptr;
Adafruit_AMG88xx amg;
Adafruit_BNO08x bno(-1);
NiclaSenseEnv *nicla = nullptr;
sh2_SensorValue_t bno_value;

bool bme_online = false;
bool amg_online = false;
bool bno_online = false;
bool nicla_online = false;
uint8_t bme_addr = 0;
uint8_t amg_addr = 0;
uint8_t bno_addr = 0;
uint32_t gps_baud = GPS_DEFAULT_BAUD;
uint32_t radar_baud = RADAR_DEFAULT_BAUD;
uint32_t gps_bytes = 0;
uint32_t radar_bytes = 0;

float qx = 0, qy = 0, qz = 0, qw = 1;
float gx = 0, gy = 0, gz = 0;
float ax = 0, ay = 0, az = 0;
float mx = 0, my = 0, mz = 0;

uint32_t last_heartbeat_ms = 0;
uint32_t last_bme_ms = 0;
uint32_t last_amg_ms = 0;
uint32_t last_bno_ms = 0;
uint32_t last_nicla_ms = 0;
uint32_t last_scan_ms = 0;
uint32_t last_ultrasonic_sample_ms = 0;
uint32_t last_ultrasonic_report_ms = 0;
int ultrasonic_mm[ULTRASONIC_COUNT] = {-1, -1, -1, -1};
const uint8_t ultrasonic_trig_pins[ULTRASONIC_COUNT] = {
  FRONT_TRIG, LEFT_TRIG, RIGHT_TRIG, REAR_TRIG
};
const uint8_t ultrasonic_echo_pins[ULTRASONIC_COUNT] = {
  FRONT_ECHO, LEFT_ECHO, RIGHT_ECHO, REAR_ECHO
};
uint8_t next_ultrasonic = 0;
char command_buffer[128];
size_t command_length = 0;
char gps_buffer[160];
size_t gps_length = 0;

bool probe(uint8_t address) {
  ATLAS_SENSOR_WIRE.beginTransmission(address);
  return ATLAS_SENSOR_WIRE.endTransmission() == 0;
}

void scanBus() {
  Serial.print("I2C,BUS="); Serial.print(ATLAS_HUB_NAME); Serial.print(",ADDRS=");
  bool first = true;
  for (uint8_t address = 1; address < 127; ++address) {
    if (!probe(address)) continue;
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

void initializeSensors() {
  bme_online = false;
  for (uint8_t address : BME_ADDRS) {
    if (!probe(address)) continue;
    if (bme == nullptr) bme = new Adafruit_BME680(&ATLAS_SENSOR_WIRE);
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
    if (probe(address) && amg.begin(address, &ATLAS_SENSOR_WIRE)) {
      amg_addr = address;
      amg_online = true;
      break;
    }
  }

  bno_online = false;
  for (uint8_t address : BNO_ADDRS) {
    if (probe(address) && bno.begin_I2C(address, &ATLAS_SENSOR_WIRE)) {
      bno_addr = address;
      bno_online = true;
      enableBnoReports();
      break;
    }
  }

  nicla_online = false;
  if (probe(NICLA_ENV_ADDR)) {
    if (nicla == nullptr) nicla = new NiclaSenseEnv(ATLAS_SENSOR_WIRE, NICLA_ENV_ADDR);
    nicla_online = nicla->begin();
    if (nicla_online) {
      nicla->temperatureHumiditySensor().setEnabled(true);
      nicla->indoorAirQualitySensor().setMode(
        IndoorAirQualitySensorMode::indoorAirQualityLowPower);
      // Outdoor sensing is enabled without persisting flash configuration.
      nicla->outdoorAirQualitySensor().setEnabled(true, false);
    }
  }

  Serial.print("I2CSTAT,HUB="); Serial.print(ATLAS_HUB_NAME);
  Serial.print(",BME="); Serial.print(bme_online ? 1 : 0);
  Serial.print(",AMG="); Serial.print(amg_online ? 1 : 0);
  Serial.print(",BNO="); Serial.print(bno_online ? 1 : 0);
  Serial.print(",NICLA_ENV="); Serial.println(nicla_online ? 1 : 0);
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

void reportNicla() {
  if (!nicla_online || nicla == nullptr) {
    Serial.println("NICLAENV,OK=0");
    return;
  }
  auto &th = nicla->temperatureHumiditySensor();
  auto &indoor = nicla->indoorAirQualitySensor();
  auto &outdoor = nicla->outdoorAirQualitySensor();
  Serial.print("NICLAENV,A=21,T="); Serial.print(th.temperature(), 2);
  Serial.print(",H="); Serial.print(th.humidity(), 2);
  Serial.print(",IAQ="); Serial.print(indoor.airQuality(), 2);
  Serial.print(",RIAQ="); Serial.print(indoor.relativeAirQuality(), 2);
  Serial.print(",ECO2="); Serial.print(indoor.CO2(), 2);
  Serial.print(",TVOC="); Serial.print(indoor.TVOC(), 4);
  Serial.print(",ETOH="); Serial.print(indoor.ethanol(), 4);
  Serial.print(",AQI="); Serial.print(outdoor.airQualityIndex());
  Serial.print(",FAQI="); Serial.print(outdoor.fastAirQualityIndex());
  Serial.print(",NO2="); Serial.print(outdoor.NO2(), 2);
  Serial.print(",O3="); Serial.print(outdoor.O3(), 2);
  Serial.println(",OK=1");
}

int readUltrasonicMm(uint8_t trig, uint8_t echo) {
  digitalWrite(trig, LOW);
  delayMicroseconds(3);
  digitalWrite(trig, HIGH);
  delayMicroseconds(10);
  digitalWrite(trig, LOW);
  const unsigned long duration = pulseIn(echo, HIGH, ULTRASONIC_ECHO_TIMEOUT_US);
  if (duration == 0) return -1;
  const long distance_mm = static_cast<long>(duration * 0.343f / 2.0f);
  return (distance_mm >= 20 && distance_mm <= 4200)
    ? static_cast<int>(distance_mm) : -1;
}

void sampleNextUltrasonic() {
  ultrasonic_mm[next_ultrasonic] = readUltrasonicMm(
    ultrasonic_trig_pins[next_ultrasonic],
    ultrasonic_echo_pins[next_ultrasonic]);
  next_ultrasonic = (next_ultrasonic + 1) % ULTRASONIC_COUNT;
}

void reportUltrasonics() {
  Serial.print("F="); Serial.print(ultrasonic_mm[0]);
  Serial.print(",L="); Serial.print(ultrasonic_mm[1]);
  Serial.print(",R="); Serial.print(ultrasonic_mm[2]);
  Serial.print(",B="); Serial.print(ultrasonic_mm[3]);
  Serial.println(",OK=1");
}

void forwardGps() {
  while (ATLAS_GPS_SERIAL.available()) {
    const char c = static_cast<char>(ATLAS_GPS_SERIAL.read());
    ++gps_bytes;
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
  if (!ATLAS_RADAR_SERIAL.available()) return;
  Serial.print("RADARHEX,");
  uint8_t count = 0;
  while (ATLAS_RADAR_SERIAL.available() && count < 64) {
    const uint8_t value = static_cast<uint8_t>(ATLAS_RADAR_SERIAL.read());
    if (value < 16) Serial.print('0');
    Serial.print(value, HEX);
    ++count;
    ++radar_bytes;
  }
  Serial.println();
}

void setGpsBaud(uint32_t baud) {
  if (baud < 1200 || baud > 921600) return;
  gps_baud = baud;
  ATLAS_GPS_SERIAL.end();
  ATLAS_GPS_SERIAL.begin(gps_baud);
  Serial.print("ACK,GPSBAUD="); Serial.println(gps_baud);
}

void setRadarBaud(uint32_t baud) {
  if (baud < 1200 || baud > 921600) return;
  radar_baud = baud;
  ATLAS_RADAR_SERIAL.end();
  ATLAS_RADAR_SERIAL.begin(radar_baud);
  Serial.print("ACK,RADARBAUD="); Serial.println(radar_baud);
}

void handleCommand(const char *command) {
  if (!strcmp(command, "PING")) {
    Serial.print("PONG,ATLAS_"); Serial.print(ATLAS_HUB_NAME); Serial.println("_SENSOR_HUB");
  } else if (!strcmp(command, "ID")) {
    Serial.print("ATLAS_"); Serial.print(ATLAS_HUB_NAME);
    Serial.print("_SENSOR_HUB,V=1,BOARD="); Serial.println(ATLAS_BOARD_NAME);
  } else if (!strcmp(command, "SCAN")) {
    scanBus();
    initializeSensors();
  } else if (!strncmp(command, "GPSBAUD,", 8)) {
    setGpsBaud(strtoul(command + 8, nullptr, 10));
  } else if (!strncmp(command, "RADARBAUD,", 10)) {
    setRadarBaud(strtoul(command + 10, nullptr, 10));
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
  for (uint8_t i = 0; i < ULTRASONIC_COUNT; ++i) {
    pinMode(ultrasonic_trig_pins[i], OUTPUT);
    digitalWrite(ultrasonic_trig_pins[i], LOW);
    pinMode(ultrasonic_echo_pins[i], INPUT);
  }
  ATLAS_SENSOR_WIRE.begin();
  ATLAS_SENSOR_WIRE.setClock(I2C_HZ);
  ATLAS_GPS_SERIAL.begin(gps_baud);
  ATLAS_RADAR_SERIAL.begin(radar_baud);
  delay(1200);
  Serial.print("ATLAS_"); Serial.print(ATLAS_HUB_NAME);
  Serial.print("_SENSOR_HUB,V=1,BOARD="); Serial.println(ATLAS_BOARD_NAME);
  scanBus();
  initializeSensors();
}

void loop() {
  const uint32_t now = millis();
  readCommands();
  forwardGps();
  forwardRadar();
  readBno();

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
  if (now - last_nicla_ms >= 5000) {
    last_nicla_ms = now;
    reportNicla();
  }
  if (now - last_ultrasonic_sample_ms >= ULTRASONIC_SAMPLE_INTERVAL_MS) {
    last_ultrasonic_sample_ms = now;
    sampleNextUltrasonic();
  }
  if (now - last_ultrasonic_report_ms >= ULTRASONIC_REPORT_INTERVAL_MS) {
    last_ultrasonic_report_ms = now;
    reportUltrasonics();
  }
  if (now - last_scan_ms >= 30000) {
    last_scan_ms = now;
    const bool sensor_offline =
      !bme_online || !amg_online || !bno_online || !nicla_online;
    if (sensor_offline) {
      initializeSensors();
    }
  }
  if (now - last_heartbeat_ms >= 1000) {
    last_heartbeat_ms = now;
    Serial.print("HEARTBEAT,HUB="); Serial.print(ATLAS_HUB_NAME);
    Serial.print(",UP_MS="); Serial.print(now);
    Serial.print(",GPS_BAUD="); Serial.print(gps_baud);
    Serial.print(",GPS_BYTES="); Serial.print(gps_bytes);
    Serial.print(",RADAR_BAUD="); Serial.print(radar_baud);
    Serial.print(",RADAR_BYTES="); Serial.println(radar_bytes);
  }
  delay(1);
}
