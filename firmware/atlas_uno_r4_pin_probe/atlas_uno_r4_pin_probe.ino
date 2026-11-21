#include <Arduino.h>
#include <Wire.h>

// TEMPORARY diagnostic only. A4/A5 and parallel SDA/SCL connections must be
// disconnected. Motor and servo power OFF. Never commands any actuator/UART.
static_assert(WIRE_SDA_PIN == 18 && WIRE_SCL_PIN == 19,
              "Probe is only for UNO R4 WiFi standard A4/A5 mapping");

void report(const char *mode) {
  uint8_t sda_high = 0, scl_high = 0;
  for (uint8_t i = 0; i < 16; ++i) {
    sda_high += digitalRead(WIRE_SDA_PIN) == HIGH;
    scl_high += digitalRead(WIRE_SCL_PIN) == HIGH;
    delay(1);
  }
  Serial.print("PINPROBE,MODE="); Serial.print(mode);
  Serial.print(",SDA_PIN="); Serial.print(WIRE_SDA_PIN);
  Serial.print(",SCL_PIN="); Serial.print(WIRE_SCL_PIN);
  Serial.print(",SDA_HIGH_OF_16="); Serial.print(sda_high);
  Serial.print(",SCL_HIGH_OF_16="); Serial.print(scl_high);
  Serial.print(",UP_MS="); Serial.println(millis());
}

void setup() {
  Serial.begin(115200);
  const uint32_t started = millis();
  while (!Serial && millis() - started < 3000) delay(10);
  pinMode(WIRE_SDA_PIN, INPUT_PULLUP);
  pinMode(WIRE_SCL_PIN, INPUT_PULLUP);
  Serial.println("ATLAS_UNO_R4_PINPROBE_V1,NO_ACTUATOR_CODE");
}

void loop() {
  pinMode(WIRE_SDA_PIN, INPUT_PULLUP);
  pinMode(WIRE_SCL_PIN, INPUT_PULLUP);
  delay(25);
  report("GPIO_PULLUP");
  Wire.begin();
  Wire.setWireTimeout(25000, true);
  Wire.setClock(100000);
  delay(25);
  report("WIRE_IDLE");
  Wire.end();
  pinMode(WIRE_SDA_PIN, INPUT_PULLUP);
  pinMode(WIRE_SCL_PIN, INPUT_PULLUP);
  delay(25);
  report("GPIO_AFTER_WIRE_END");
  delay(1000);
}
