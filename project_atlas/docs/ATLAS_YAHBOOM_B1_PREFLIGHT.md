# ATLAS Stage 28, B1 pre-flight: Yahboom board firmware backup and recovery (no hardware action taken)

Date: 2026-10-27. All of this was analysis, offline builds and read-only Jetson queries: sysfs, udev, journal and `/api/estop/state`. Nothing was opened on the board's serial port, no service was stopped, nothing was flashed, and the wiring is unchanged. The E-STOP is latched and the SBUS lead stays isolated.

## Verdict

| Gate | Decision | Why |
|---|---|---|
| **B1 (read-only backup)** | **GO, conditional** on the owner preconditions below | Read-only tool built and tested against a simulated bootloader; the procedure is physical-entry only; the only system change is one stop and start of `rover-base-telemetry` |
| **B2 (flash)** | **NO-GO** until B1 results are in | Need the read-protection (RDP) state, chip identity and readback-vs-3.6.5 comparison, plus a toolchain decision |
| GCC image for B2 | **Conditional** | Static audit now passes, but only after two fixes found today (section 5) |

### Owner preconditions for B1

1. **How is the Jetson powered?** If it is fed from the Yahboom board's DC 5V output, the board's main switch must stay ON during B1. Isolation is then done by unplugging connectors only.
2. Unplug drive motor connectors M1–M4 and **both steering servos** (PWM S1 = rear, S2 = front). See section 8: B1 is now done with the main switch ON, and isolation is by unplugging actuators.
3. Photograph the MCU marking (STM32F103RCT6 or APM32E103RET6, see section 1). The tool also reads the chip ID, so this is a cross-check.
4. Approve one stop and start of `rover-base-telemetry` (about 3–5 minutes). The dashboard will show the base offline; the E-STOP stays latched.

## 1. MCU, memory and bootloader access (sources: Yahboom V3.0 schematic 2025-05-09, vendor source)

| Item | Finding | Evidence |
|---|---|---|
| MCU | Footprint marked **"APM32E103RET6/STM32F103RCT6"**, so either part can be fitted | Schematic U11 |
| Flash/RAM | STM32F103RC: 256 KB / 48 KB. APM32E103RE: 512 KB / 128 KB. Both use 2 KB pages. | Datasheets. The tool reads `F_SIZE` (0x1FFFF7E0) instead of assuming. |
| Vendor image | 0x08000000–0x080163EF (91 120 B). Settings in **sector 120 = 0x0803C000** | 3.6.5 hex, `app_flash.h` |
| Settings layout | test mode +0x00, reset marker 0xAA55 +0x02, car type +0x04, auto-report +0x06, IMU +0x0A, RGB +0x10, yaw PID +0x20, motor PID +0x30 (u16 ×1000), arm offsets +0x50, **AKM default angle +0x70** | `app_flash.c/.h` |
| Bootloader | ROM system bootloader on **USART1 (PA9/PA10) = the CH340N on the micro-USB**. BOOT1 is pulled down (R31 100k). | Schematic |
| Entry | **Physical only**: hold BOOT0 (S4), press RESET (S2), release BOOT0. The CH340N **RTS pin is not connected** and it has no DTR, so no software can reset the MCU or enter the bootloader by accident. The FlyMcu "DTR/RTS" option does nothing on this board. | Schematic, USB communication block |
| SWD | J16: +3.3 V, SWCLK, GND, SWDIO, GND. **No NRST**, so connect-under-reset is impossible | Schematic |
| USB identity | `/dev/ttyUSB0`, location `1-2.2.3`, 1a86:7523 (GPS 1-2.4.2, IMU 1-2.4.3) | pyserial `list_ports`, read-only |
| Power in B1 | Micro-USB VCC → SS34 → 5 V rail → 3.3 V LDO. **The MCU and CH340 run from the Jetson's USB with the main switch OFF**, while VM (motors, 6.8 V servo rail) is cut by PMOS Q2. Motor drivers are AM2861/AM2857-class with 30 kΩ input pull-downs (floating inputs mean Stop). The datasheet warns floating inputs can mis-trigger when hot, hence motor rail off or motors unplugged. | Schematic power block, AM2857 datasheet |
| Low-battery latch | Firmware latches `System_Enable = 0` after about 2 s below 9.6 V, so it must be **restarted with the main switch ON** | `app_bat.c` |

## 2. Is vendor 3.6.5 compatible with ATLAS (hardware V3.0, car type 5)?

**What ATLAS sends:** `yahboom_base` uses `set_car_type(5)`, `set_auto_report_state(True, False)`, `set_motor` (FUNC_MOTOR, raw PWM), `set_pwm_servo` ×2 (rear S1, front S2). It reads the auto-reports and the version and car-type requests. It **does not** use FUNC_MOTION, Ackermann or PID commands; closed-loop control runs on the Jetson.

**Comparison with 3.5.1** (the only other published production source):
- `bsp_motor.c`, `bsp_pwmServo.c`, `bsp_usart.c`, `bsp.c` and `app.c` are identical.
- In `protocol.c`, the FUNC_MOTOR, FUNC_PWM_SERVO, FUNC_CAR_TYPE and FUNC_AUTO_REPORT handlers are unchanged. The only changes add A1 car-type branches.
- 3.6 changes that touch car type 5 apply only to `Ackerman_Ctrl` (the FUNC_MOTION and SBUS path): no wheel reversal at low speed.

So for the commands ATLAS uses, 3.6.5 behaves exactly like 3.5.1 and like the "3.6" that ATLAS runs now, which reports major.minor only.

**ICM20948 / V3.0 hardware:** supported since V3.3 (auto-detects ICM20948 or MPU9250), and the board's V3.0 introduction requires library 3.3.x or later. The auto-report mix (speed, ICM raw, attitude, encoder every 40 ms) matches ATLAS's measured 4.0 packets per encoder packet.

**Car-type side effects to know about:**
- At boot, car type 5 from flash drives **PWM S1 (ATLAS rear steering) to the AKM default angle**: flash +0x70, default 90, which equals ATLAS's rear centre of 90.
- `Flash_Set_CarType` writes flash only if the value changes. The Jetson's per-start `set_car_type(5)` does not wear the flash.

**Release-hex provenance:** `rosmaster_V3.6.5.hex` is binary-identical to `output/rosmaster_V3.6.5.hex` inside the source zip. The build stamp `Aug 29 2025 15:36:59` matches. A Keil ARMCC build cannot be reproduced bit-for-bit here.

## 3. Backup plan (B1, read-only)

`tools/diagnostics/stm32_readback/b1_run.sh` (interactive; owner present):

1. Software preconditions: E-STOP latched, `/dev/ttyUSB0` at USB `1-2.2.3`, vendor hex hash.
2. **Jetson-side backup first.** ATLAS's steering calibration (`steering_calibration.json`: front 90/121/50, rear 90/134/59), `drive_pid.yaml`, encoder and IMU calibration all live on the Jetson, not the board. They are copied with SHA256SUMS, along with the script hashes and the last "board ready" log line.
3. Owner: isolation (precondition list above).
4. `systemctl --user stop rover-base-telemetry`, then confirm with `fuser` that the port is free.
5. Owner: BOOT0 + RESET.
6. `atlas_stm32_readback.py` (AN3155, **whitelist 0x7F/0x00/0x01/0x02/0x11 only**):
   - sync, GET, GET_VERSION, GET_ID;
   - option bytes (RDP probe), F_SIZE, UID;
   - **the whole flash read twice and compared**;
   - writes `flash_full.bin` and `.hex`, option bytes, `settings_sector120.bin` decoded to JSON, SHA256SUMS, and a byte comparison with vendor 3.6.5;
   - refuses if the board is still sending normal firmware packets (not in the bootloader);
   - first NACK or timeout stops the run, with no retry.
7. Owner: main switch ON, RESET (no bootloader GO). Then start `rover-base-telemetry` and check "Yahboom board ready … firmware=3.6, car_type=5".

**Board-side configuration captured:** the full flash including sector 120: car type, auto-report, yaw and motor PID, arm offsets, AKM default angle, reset marker.

**Rollback for B1:** nothing on the chip is changed. The single system change is reversed by step 7. If the script stops anywhere, it prints the same three restore steps.

## 4. Read-protection check without unlock

- **RDP active:** `READ_MEMORY` is refused (NACK). The tool records `read_protection: ACTIVE`, exits with code 3, and does nothing else.
- **RDP inactive:** the option-byte RDP value is 0xA5, which is recorded.
- **0x92 READOUT_UNPROTECT** (which mass-erases), erase, write, write-protect changes and GO are **refused in code before a byte is sent**. Tests cover all 8 destructive commands, and a static source check finds none of their values.

## 5. GCC image vs vendor build (offline audit, `firmware/yahboom_rc_report/audit_gcc_image.py`)

| Check | Result |
|---|---|
| Vendor build settings (uvprojx) | ARMCC 5.06u7, **-O1**, short enums, unsigned char, MicroLIB. The GCC build now matches with `-O1 -fshort-enums -funsigned-char -fno-strict-aliasing`. |
| Interrupt vectors | **Identical set** to the vendor hex: Reset, SVC/PendSV/SysTick → FreeRTOS, EXTI4 (IMU), TIM7, USART1/2/3, USB_LP_CAN1_RX0. Vendor fault handlers are `B .` stubs; GCC uses one Default_Handler loop, which behaves the same. |
| NVIC | Group 2. USART1 is preempt 1/sub 3 and USART2 is preempt 1/sub 2, i.e. **0x60–0x70, above** `configMAX_SYSCALL_INTERRUPT_PRIORITY` 0xBF. No ISR reaches a FreeRTOS API (verified for all 6). |
| DMA | USART1 TX on DMA1 Ch4, polled (`DMA_GetCurrDataCounter`), no DMA IRQ. Same source, so the new report waits for the previous transfer exactly as existing packets do. |
| FreeRTOS | Same kernel source 10.4.3-LTS-P1 and same config. Only the port layer differs (GCC ARM_CM3 instead of RVDS). Note: `configMAX_PRIORITIES` is 5 while tasks request priorities 7–10, so the kernel clamps them to 4 in **both** builds (vendor behaviour). |
| IMU | InvenSense MEMS library compiled from source (no ARMCC binary libraries in the project). No implicit function declarations with `-Wall`. Remaining warnings are vendor-inherent and present in the Keil build too. |
| Motor control | `bsp_motor`, `app_motion` and protocol handlers are unchanged. The patched `SBUS_Handle`, `SBUS_Send_Report` and `SBUS_Reveive` have no path to motion, motor or servo code. |
| Image size | GCC image ends at 0x0801B693 (< 0x0803C000), so a page-erase flash keeps sector 120 |
| **Task stacks** | **Fixed (was NO-GO).** With newlib-nano printf and GCC libm, static worst case overflowed 3 vendor stack sizes: Control 512 B needs ~944 B (Ackermann `tan()` path, and the `set_car_type` printf path ~484 B on every base start); Key and App_Handle 512 B need ~464–480 B. `atlas_gcc_compat.patch` raises them to 1536/1024/1024 B and FreeRTOS heap from 17 KB to 20 KB (need ~15.3 KB). It also fixes a vendor 2-byte stack overflow in the OLED build-date `sprintf` (`text[20]` to `[24]`). |
| **My Stage 28 patch** | **Fixed.** v1 called `xTaskGetTickCountFromISR` inside USART2 (priority 0x60, above the syscall ceiling) and relied on `taskENTER_CRITICAL`, which cannot mask that IRQ. v2: the ISR only bumps seq and ever; the tick is stamped in task context every 1 ms; the report copies the frame under PRIMASK (< 2 µs). |

**Not verifiable offline (B3 must cover):**
- run-time timing;
- the soft-float library's numeric differences;
- float `printf` on the OLED (newlib-nano shows blank floats; OLED only);
- indirect calls (not in the stack estimate);
- real IMU init on the actual chip, especially if it is an APM32.

## 6. Recovery if flashing fails

- **The ROM bootloader cannot be erased or overwritten**, and entry is physical (BOOT0 + RESET). Any interrupted or bad flash is recovered by re-entering the bootloader and writing an image again, over the same micro-USB link (stm32flash on the Jetson, or FlyMcu or STM32CubeProgrammer on the PC), or over SWD.
- **Restore images, in order of preference:**
  1. the B1 readback (`flash_full.hex`, exact factory image plus settings);
  2. vendor `rosmaster_V3.6.5.hex`, then let the Jetson rewrite car type 5 on start.
- **If B1 finds RDP active:**
  - No backup is possible.
  - Flashing anything first requires READOUT_UNPROTECT, which **mass-erases** the chip. That needs its own explicit approval.
  - After that, the exact factory image is gone; the restore path is vendor 3.6.5.
  - What ATLAS needs from the board's settings survives:
    - car type: the Jetson rewrites 5 at each start;
    - AKM default angle: firmware default 90 = ATLAS rear centre;
    - auto-report: default 1, and the Jetson enables it anyway;
    - motor PID: not used by ATLAS's raw-PWM path.
- **If the chip is APM32E103 rather than STM32:** the same protocol and page size apply. Its chip ID and flash size are recorded in B1 and must be reviewed before B2.
- **Failure that recovery cannot fix:** electrical damage. That is mitigated by the isolation preconditions (motors and servos unplugged, motor rail off).
- **Jetson side:** `tools/deploy/stage28_yahboom_rc/rollback.sh` gives a byte-identical restore (rehearsed).

## 7. Offline tests (this stage)

- `tests/test_stm32_readback.py`, 17 tests:
  - full backup with two identical passes, settings decode, Intel-hex output and the vendor comparison;
  - 512 KB part;
  - RDP active is reported and never unlocked;
  - first NACK stops with no retry;
  - silent port times out;
  - unknown chip ID is flagged;
  - all 8 destructive commands refused before send, and the static source check;
  - CLI refuses without confirmation or on a wrong port.
- The Stage 28 tests are re-run against patch v2.
- `build_gcc.sh` applies both patches and runs `audit_gcc_image.py`: every check OK, exit 0. Without the compat patch the audit FAILs the three task stacks, as intended.

## 8. Power arrangement and backfeed analysis (2026-10-27 10:30 update, read-only)

The owner reports the Jetson is powered by a separate LTC3780 buck-boost, not by the Yahboom 5 V output. That still needs confirming at the hardware: **where does the LTC3780 input come from?**

| Path | Finding (V3.0 schematic) | Consequence |
|---|---|---|
| Jetson USB VBUS → board | Micro-USB VCC → D5 (SS34) → board 5 V rail → AMS1117 3.3 V (MCU, CH340N) | The MCU runs from USB when the board is unpowered |
| Board 5 V → Jetson USB | Blocked by D5 | No backfeed into the Jetson's USB port |
| Board 5 V rail → VM (motor rail) | U6 MP2225 is a synchronous buck; its high-side FET body diode conducts SW→IN. When the 5 V rail is USB-fed and VM is unpowered, **VM is very likely back-fed to about 4 V**. | **Main switch OFF does NOT guarantee motor rail = 0 V.** Not measured. |
| VM → servo 6.8 V rail | U7 MP2225 (EN tied to VM) | A back-fed VM can reach the servo rail |
| VM → J12/J14 "DC 12V output" (XH 2P), motor drivers AM2861, BAT sense | All on VM, after the PMOS main switch Q2 | Anything on J12/J14 would be powered from the **Jetson's USB** with the switch off. If the LTC3780 input were taken from J12/J14, switching the board off would drop the Jetson. |
| VM → IN12V | Q2 PMOS body diode, only if the battery is disconnected | The battery connector pins could sit at about 4 V when unplugged |
| 5 V rail outputs | CON3 (5 V out), Type-C (IP2723T/Q7), RGB strip, serial-servo buffer, PWM servos on the 5 V jumper position, **SBUS header V pin (5 V)** | All become USB loads with the switch off |

USB topology, read-only: the board's CH340 is on self-powered hub 1-2.2 (bmAttributes 0xE0), together with the RPLIDAR CP2102 (1-2.2.1) and the ESP32 (1-2.2.4). The board's VM sense reads 12.3 V now, so the battery is connected and the main switch is ON.

**Decision: B1 is done with the board main switch ON and the battery connected.** The switch-OFF variant is withdrawn because of the backfeed above. With the switch ON:
- VM is a known 12 V;
- there is no USB backfeed load;
- there is no low-battery latch;
- isolation is achieved by physically unplugging every actuator.

### Isolation checklist (owner, before requesting B1 approval)

1. Wheels lifted clear of the floor. E-STOP latched (Xbox B). FlySky transmitter OFF.
2. SBUS lead: signal wire unplugged and insulated. Recommended: unplug the whole 3-pin lead (its V pin is board 5 V).
3. Drive motors M1–M4: all four PH-6P motor/encoder connectors unplugged at the board.
4. PWM servos S1 (rear steering) and S2 (front steering), plus any S3/S4: unplugged at J7.
5. Serial-servo port J10, RGB strip J15, CAN J11: unplugged, or confirmed empty.
6. Inventory of J12/J14 (DC 12V out), CON3 (5 V out) and the Type-C port: record what is plugged in. **Trace the LTC3780 input + wire** and confirm it goes to the battery/BMS side, **not** to J12/J14 or anything after the board switch.
7. Multimeter checks, switch ON, nothing else changed:
   - VM at J12/J14 pin 1 ≈ battery voltage (≈ 12.3 V now);
   - LTC3780 input ≈ battery voltage;
   - with motor connectors unplugged, nothing measurable at the motor-side plugs.
8. BOOT0 (S4) and RESET (S2) buttons physically reachable without disturbing the micro-USB cable.
9. MCU marking photographed (STM32F103RCT6 or APM32E103RET6).

### Backup and recovery requirements (all must be true before B2 is even discussed)

| # | Requirement | Status |
|---|---|---|
| R1 | Chip identity known (marking photo and B1 GET_ID / F_SIZE) | Pending (owner, then B1) |
| R2 | B1 readback with two identical passes, SHA256SUMS, settings decoded | Pending (B1) |
| R3 | RDP state known; **no unlock without separate approval** | Pending (B1) |
| R4 | Restore images stored on the Jetson **and** the PC: B1 readback and vendor 3.6.5 hex (sha256 `088af519…2b55b`) | Pending |
| R5 | A flashing path that does not need the Jetson (PC + micro-USB + FlyMcu or STM32CubeProgrammer), and optionally ST-Link for SWD (header has no NRST) | Owner to confirm |
| R6 | Jetson-side calibration backed up with hashes (steering, drive PID, encoder, IMU). This is done as step 1 of `b1_run.sh` | Ready |
| R7 | Known-good return-to-service reference: "board ready firmware=3.6, car_type=5", 4.0 packets per encoder packet, 0 checksum errors, board battery reading ≈ BMS | Recorded in B3 template |
| R8 | B2 approval is separate; this document does not request it | — |
