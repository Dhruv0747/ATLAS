# ATLAS Portenta H7 Lite Sensor Hub

## Purpose

The Portenta H7 Lite is a deterministic sensor I/O coprocessor. It collects
I2C, GNSS, and radar telemetry and sends framed data to the Jetson over USB.
Nav2, safety, collision avoidance, command multiplexing, and motor control stay
on the Jetson. The Portenta has no motor-command authority.

## Reserved interfaces

| Function | Arduino interface | Portenta Breakout pins |
|---|---|---|
| External sensor bus | `Wire2` / I2C2 | J2-45 SDA, J2-47 SCL |
| GNSS | `Serial2` / UART2 | J2-26 TX, J2-28 RX |
| RD-03D radar | `Serial3` / UART3 | J2-25 TX, J2-27 RX |
| Jetson link | USB CDC | USB-C on the Portenta module |

## Four ultrasonic sensors

The Portenta firmware scans the sensors sequentially to reduce acoustic
crosstalk. Connect the rover sides exactly as labelled here; unlike the legacy
UNO harness, the Portenta bridge does not swap left and right.

| Rover sensor | Trigger (Arduino / Breakout) | Echo (Arduino / Breakout) |
|---|---|---|
| Front | D0 / J2-62 `PWM 7` | D1 / J2-60 `PWM 6` |
| Left | D2 / J2-67 `PWM 5` | D3 / J2-65 `PWM 4` |
| Right | D4 / J2-63 `PWM 3` | D5 / J2-61 `PWM 2` |
| Rear | D6 / J2-59 `PWM 1` | D7 / J2-36 `SPI1 CS` |

For each HC-SR04-compatible sensor:

- `VCC` goes to a regulated 5 V sensor supply and `GND` goes to common ground.
- `TRIG` connects directly to its assigned Portenta digital output.
- `ECHO` must pass through a 5 V-to-3.3 V level shifter or resistor divider
  before reaching the assigned Portenta input. Never connect a 5 V Echo output
  directly to the Portenta.
- A simple divider per Echo uses 1 kOhm from sensor Echo to the Portenta input
  and 2 kOhm from the Portenta input to GND (approximately 3.33 V at 5 V Echo).
- Power all four sensors from the regulated 5 V rail, not from a GPIO pin.

Power off both boards before changing the harness. Validate one sensor at a
time in this order: front, left, right, rear.

`Wire1` is reserved for Portenta internal PMIC/crypto hardware and must not be
used as the ATLAS external sensor bus.

## Electrical rules

- Portenta GPIO, I2C, and UART logic is 3.3 V. Never apply 5 V to a signal pin.
- All devices must share ground.
- Attach only one new device at a time and run `SCAN` after each attachment.
- Use one set of I2C pull-ups to 3.3 V (typically 2.2–4.7 kOhm) if the modules do
  not already provide suitable pull-ups.
- Keep the I2C harness short and route it away from motors, servo power, and the
  5G modem. Start at 100 kHz; reduce to 50 kHz only if measured errors require it.
- Power the Nicla Sense Env through its documented ESLOV/+5 V input. Its I2C
  signals remain 3.3 V. Do not improvise power from a signal header.
- Confirm each module's supply requirement before wiring GPS or radar.

## Planned migration sequence

1. Upload and validate the Portenta firmware with no external sensors.
2. Connect the I2C devices one at a time: Nicla Sense Env, BME680, AMG8833,
   then BNO08x/PCA9685 if they are retained.
3. Confirm unique I2C addresses and stable telemetry for at least 10 minutes.
4. Move the L76K GNSS to UART2 and validate NMEA/fix reporting outdoors.
5. Move the RD-03D radar to UART3 and validate every target against its former
   direct-USB feed.
6. Only after parity is proven, disable the old UNO/direct sensor services and
   enable `atlas-portenta-sensor-hub.service`.

Never move every sensor at once; that would make wiring, address, power, and
protocol faults difficult to isolate.

## Firmware build

```powershell
arduino-cli compile --fqbn arduino:mbed_portenta:envie_m7 firmware/atlas_portenta_h7
```

Do not upload until the board is positively identified as an Arduino Portenta.
The expected application USB identity from the installed official core is
VID:PID `2341:025b`.

## Jetson activation (later, after hardware validation)

```bash
sudo bash /home/jetson/project_atlas/scripts/install_atlas_portenta_udev_root.sh
systemctl --user daemon-reload
systemctl --user enable --now atlas-portenta-sensor-hub.service
```

The old UNO/direct sensor bridge must be stopped before enabling the Portenta
bridge, otherwise duplicate ROS publishers can corrupt sensor selection.

## USB protocol

The firmware emits compatible `BME`, `AMG`, `BNO`, and `GPS` records plus:

- `ATLAS_PORTENTA_SENSOR_HUB,...` identity
- `I2C,...` and `I2CSTAT,...` discovery/health
- `NICLAENV,...` complete Nicla environmental readings
- `RADARHEX,...` framed radar bytes
- `HEARTBEAT,...` link and byte counters

Supported commands are `PING`, `ID`, `SCAN`, `GPSBAUD,<rate>`, and
`RADARBAUD,<rate>`.
