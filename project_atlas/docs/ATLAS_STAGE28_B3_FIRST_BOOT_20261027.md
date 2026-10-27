# Stage 28 B3 first normal boot — passive verification

2026-10-27. **PASS for first boot and passive USB telemetry only.** No actuator/output electrical validation or driving claim.

Owner approved one normal reset; freshly confirmed BOOT0 released, actuators unplugged, transmitter OFF, stable power and Windows USB. B2 evidence was rechecked (programming/readback PASS; settings and option fields unchanged). Receive-only COM26 at115200 8N1 was armed before the separately guided owner RESET. No serial writes, software reset, firmware write, Jetson deployment or retry occurred.

## Observed result

- One banner `Firmware Version: V3.6.161` (expected patch marker0xA1), one scheduler-start marker, seven task-start messages. No repeated boot banner or ICM_INIT ERROR during this observation.
- IMU Type0 maps to ICM20948 in source. 818 raw IMU packets and818 attitude packets,817 distinct payloads in each stream. This supports initialization/data delivery, not calibration accuracy or navigation suitability.
- 818 speed/battery packets: all reported velocities zero. First two battery values zero during initialization; subsequent values12.4–12.5V. No independent voltage-meter comparison was performed.
- 817 encoder packets, all four counters zero. Connectors are disconnected; this does not validate encoder response under movement.
- 817 Stage28 SBUS report packets. Every status0x10 indicates direct drive disabled with no SBUS frame ever received. Transmitter remained OFF; live channel reception is not yet verified.
- 4088 complete packets, zero checksum errors and zero unexplained bytes after initial ASCII startup. One incomplete header byte at the capture boundary is retained, not classified as corrupt.
- Capture45.0085seconds from first received startup data,81508bytes. Startup had10.9568seconds between settings output and Hello/scheduler. No claim about exact internal source of that pause. After binary telemetry began, maximum host chunk gap0.011374seconds. Windows receipt timestamps are not MCU timestamps.

## Settings and limitations

Startup loaded reset marker0xAA55, steering centre90, car type5, automatic report1, PID0.800/0.060/0.500, servo medians2000/2000/2000/2000/1486/3100. Each matches the decoded original settings-page backup. No default-reset marker was observed. B2 established byte-for-byte preservation before boot; passive startup cannot prove every flash byte remains unchanged after startup. Jetson calibration archive was untouched.

No host motor commands were sent; telemetry showed no motion, but disconnected encoders and receive-only telemetry cannot prove PWM/servo pins electrically inactive. Existing vendor startup initialization remains present. Keep all actuators disconnected. Software E-STOP on the shut-down Jetson is not enforcing board outputs.

## Evidence and stopped test state

Private directory `C:/Users/Dhruv/Documents/Codex/2026-07-24/h/work/stage28-b3-passive-20261027/` contains capture_once.py, raw.bin, monotonic chunk records, startup text, result.json, analysis.json, original-settings decode and SHA256SUMS.

Raw capture SHA256 `1409aff6fef80689eb69ab5139be9218a57fd08466a26643e64b66726bf7a5db`. Capture closed COM26 after45seconds of observation. Board remains powered in normal firmware; no second reset requested or executed.

Next gate: request separate approval for a bounded stationary FlySky transmitter-ON/channel-report test, with all actuator connectors still unplugged. Do not activate transmitter, reconnect outputs, write settings, deploy Jetson code or conduct movement under B3 approval. If the owner prefers returning USB to Jetson first, that is a separately guided connection/service-validation stage.
