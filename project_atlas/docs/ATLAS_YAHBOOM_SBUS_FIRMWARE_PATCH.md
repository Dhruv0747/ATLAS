# ATLAS Stage 28: direct SBUS through the Yahboom board (prepared offline, NOT flashed, NOT deployed)

Date: 2026-10-27. Branch `agent/sync-developer-20261011`.

Nothing was flashed, deployed, restarted or energised. The transmitter stayed off and the E-STOP stayed latched (`/api/estop/state` → `latched: true`). The Jetson was only read: hashes, udev properties, service units and process file handles.

Architecture: FS-i6S → FS-iA10B (SBUS) → Yahboom STM32F103RCT6 USART2 → patched firmware → existing CH340 (USART1, 115200) → `yahboom_base.py` (sole port owner) → `/atlas/rc/frames` → FlySky Test Lab.

## 1. Vendor firmware found

| Item | Where | Evidence |
|---|---|---|
| **Production source 3.6.5** `ROS-Driver-Board-FW-master.zip` (sha256 `3d7a6e1c…0687e`) | Yahboom Drive, ROSMASTER-A1 → Code-Firmware → "STM32 firmware expansion board" | `bsp.h` VERSION 3.6.5; CHANGELOG V3.6; Keil project `rosmaster.uvprojx`, ARMCC 5.06u7 |
| **Release hex 3.6.5** `rosmaster_V3.6.5.hex` (sha256 `088af519…2b55b`) | Same folder | Binary-identical to `output/rosmaster_V3.6.5.hex` inside the source zip. Build stamp `Aug 29 2025 15:36:59` matches the source files (2025-08-29). |
| Older production source and hex 3.5.1 | ROS-Driver-Board → Code → "Factory STM32 firmware" (also in the RDK-X5 folder) | Not used |
| SBUS tutorial (1.6) | `4.board.zip` → `SBUS/` | **Demo only**: prints channels on USART1 and has no motor, IMU or protocol code. Not a substitute. |
| `jmanuelc87/bolt` | GitHub | Third-party rewrite, CAN-only, no SBUS. Not a substitute. |

The URLs and hashes are in `firmware/yahboom_rc_report/VENDOR.sha256`. `fetch_vendor.sh` re-downloads and verifies them. Vendor files are **not committed** to the ATLAS repo.

### Coverage check of the 3.6.5 source

| Requirement | File |
|---|---|
| SBUS decoding | `Source/APP/app_sbus.c` (USART2 RX ISR → `SBUS_Reveive`, `SBUS_Parse_Data`) |
| Motor control | `app_motion.c`, `bsp_motor.c` |
| Encoders | `bsp_encoder.c` |
| Motor PID | `app_pid.c`, `TOOL/tool_pid.c` |
| ICM20948 / IMU | `MEMS/icm20948.c` and InvenSense libraries, `bsp_mpu9250.c` |
| Ackermann steering | `app_ackerman.c` (car type 5 = `CAR_ACKERMAN`, ROSMASTER R2) |
| Battery | `app_bat.c`, `bsp_adc.c` |
| USB serial protocol | `protocol.c`, `bsp_usart.c` (USART1 DMA). Auto-report every 40 ms: speed, ICM raw, attitude, encoder. This matches the 4.0 packets-per-encoder measured on ATLAS. |

**Version gap:** ATLAS reports `firmware=3.6`, but the board sends only major.minor (`Bsp_Send_Version`), so the patch digit is unknown. 3.6.5 is the only 3.6 Yahboom publishes. The exact image on ATLAS can only be known by reading the flash back (gate B1).

## 2. Direct-drive risk: confirmed in source

In vendor 3.5.1 and 3.6.5, `vTask_Control` calls `SBUS_Handle()` every 1 ms. For car type 5 it does the following on **every** received SBUS frame:

```
value_x = -(CH3 - 1000); value_z = CH1 - 1000;  dead band ±60
Ackerman_Ctrl(value_x * 2.3, value_z / 18, 0)    -> motors up to ±2000 (AKM_MOTOR_MAX_SPEED), steering ±45°
all sticks centred -> Motion_Stop(CH6 < 500 ? FREE : BRAKE) for 100 frames, then free stop
SBUS failsafe/frame-lost flag -> CH1..CH4 forced to centre -> stop
```

It does not check the host link or the E-STOP. The Jetson cannot override it, because SBUS frames arrive at about 70–140 Hz and the Jetson's keepalive runs at 10 Hz.

**The FS-i6S hazard:** the throttle stick (CH3, Mode 2) does not self-centre. Left at the bottom, it sits far below 1000, so `value_x` is large and positive. That is close to full forward speed the moment the transmitter links.

**Until the patched firmware is flashed:**
- the receiver's SBUS signal wire stays disconnected and insulated;
- the transmitter stays off.

## 3. Firmware patch (`firmware/yahboom_rc_report/atlas_rc_report.patch`)

The patch changes 6 files: +83 lines, and only 2 vendor lines modified.

| Change | Purpose |
|---|---|
| `config.h`: `ENABLE_SBUS_DRIVE 0`, `ENABLE_SBUS_REPORT 1` | Feature switches |
| `app_sbus.c`: the drive block is now `#elif ENABLE_SBUS_DRIVE` | **SBUS→motion is compiled out.** The patched `SBUS_Handle` calls only `SBUS_Parse_Data`, verified by disassembly. |
| `app_sbus.h`: `#define ALL_CHANNELS` | Parses CH9–CH16 (vendor default parsed 8) |
| ISR: `seq`, `ever`, tick of the last complete frame | Freshness |
| `SBUS_Build_Report` / `SBUS_Send_Report` | Copies the frame inside `taskENTER_CRITICAL` and sends one packet |
| `app.c`: slot 36 of the 40 ms auto-report cycle | 25 Hz, 5 ms after the encoder packet. USART1 DMA waits for the previous transfer. |
| `protocol.h`: `FUNC_REPORT_RC_SBUS 0xE1` | Unused, private range, MCU→host only |
| `bsp.h`: `VERSION_PATCH 0xA1` | Shown as V3.6.161 on OLED and boot banner. The host identifies the firmware by the report format byte, since the version packet carries only 3.6. |

**Packet layout (32 bytes, existing framing):**

```
FF FB 1E E1 | A1 seq status age10 | SBUS bytes 1..23 (unmodified) | sum(bytes[2:31]) & 0xFF
```

Status bits:
- bit0: a frame was ever received
- bit1: fresh (younger than 100 ms)
- bit2: frame-lost flag
- bit3: failsafe flag
- bit4: **drive disabled** (always 1 in this build; the Jetson refuses reports without it)

**Link load:** about 1.7 kB/s today, rising to about 2.5 kB/s (+0.8 kB/s) against 11.5 kB/s capacity.

**Unchanged:** every existing report and command, flash data (sector 120 at 0x0803C000, PID, car type, steering angle), the IMU and encoders.

**Behaviour when SBUS is unplugged or lost:** reports continue with `fresh = 0` and the age growing. No motion is ever produced.

**Toolchain:**
- The vendor build is Keil ARMCC 5.06. The MDK-Lite 32 KB limit is too small for this ~91 KB image.
- `build_gcc.sh` builds both pristine and patched 3.6.5 with arm-none-eabi-gcc 13.2, using the FreeRTOS 10.4.3-LTS GCC port and the ST CMSIS startup.
  - Patched image: text 102 468 B / 256 KB flash, RAM 26 KB / 48 KB.
- A GCC image is **not** bit-identical to Yahboom's. Flashing one is a new-toolchain change and needs the full gate B3 regression. Building the patch with Keil MDK on your PC is the alternative.

## 4. Jetson side (gate G-J, dormant until the firmware is flashed)

- `scripts/atlas_yahboom_rc_report.py`: a pure decoder. It rejects drive-enabled firmware and forwards only **new, fresh** frames, so a repeated stale frame can never look LIVE. It reuses Stage 27's `FrameForwarder` (20 Hz cap, immediate on flag change) and message schema.
- `insert_rosmaster_rc.py`: additive. `Rosmaster_Lib` stores the 0xE1 payload. No writes, no existing branch changed. Factory firmware never sends 0xE1.
- `insert_rc_hooks.py`: additive. `yahboom_base.py` gets one publisher (`/atlas/rc/frames`) and one 10 Hz timer. There are no subscriptions and no commands. `ATLAS_RC_REPORT=0` disables it, and missing modules leave the driver running.
- Unchanged:
  - the Xbox `/joy` path, remote stop, E-STOP, mixer, keepalive, odometry and Nav2;
  - the FlySky Test Lab;
  - `FLYSKY_DRIVE_ENABLED = False`.
- `tools/deploy/stage28_yahboom_rc/apply.sh` / `rollback.sh` refuse to run unless:
  - you have approved;
  - the live hashes are exactly `355ac420` (Rosmaster_Lib), `c551be00` (yahboom_base) and `3e4b379e` (flysky core);
  - the E-STOP is latched.
  
  They back up to `~/project-atlas-migration/stage28_rc_<stamp>` and restart **only** `rover-base-telemetry`. Rehearsed on copies of the live files: refusals worked and the rollback was byte-identical.

## 5. USB identity hazard (gate G-U)

- **Installed** `/etc/udev/rules.d/99-atlas-ch340-ports.rules` matches `ID_PATH …0:2.2:1.0`. The board is at `…0:2.2.3:1.0`, so `/dev/atlas-yahboom` does not exist. This fails closed.
- **Repo/Jetson source** `udev/99-atlas-ch340-ports.rules` matches `ID_SERIAL=1a86_USB_Serial`. That matches **all three** CH340s (Yahboom, GPS, IMU), and the last one to enumerate wins. It must never be installed.
- **`resolve_yahboom_port()` fallback** includes `/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0`, which currently points at the **GPS**. The live service avoids it only because it runs with `ATLAS_YAHBOOM_AUTO_USB=1` (protocol-verified discovery).
- **Proposed fix:**
  - `udev/99-atlas-ch340-ports.rules.stage28-proposed`: topology-pinned (`2.2.3`) `atlas-yahboom` hint only. It does not recreate `/dev/yahboom`, which older helper scripts open unverified.
  - `harden_yahboom_port.py`: the non-auto path accepts only `ATLAS_YAHBOOM_PORT` or `/dev/atlas-yahboom`.
  - Protocol verification (`open_verified('yahboom')`) remains the authority. It still recognises the board with 0xE1 reports interleaved (tested).

## 6. Offline tests

Stage 28: 24 new tests, all passing.
- `tests/test_yahboom_rc_report.py` (15):
  - packet round trip and flags;
  - firmware C `SBUS_Build_Report`, compiled from the patch and run against the Python mirror over 400 cases;
  - malformed and drive-enabled packets rejected;
  - factory and patched `Rosmaster_Lib` parse an interleaved stream with 0 checksum errors and unchanged encoder values;
  - USB discovery still works;
  - forwarding stays at or below 20 Hz, with no stale or repeated publishing;
  - Test Lab reaches LIVE, then FAILSAFE, then LOST.
- `tests/test_stage28_yahboom_hooks.py` (9):
  - hooks are additive and publish-only, with no forbidden calls;
  - timer order is preserved;
  - the hook method publishes new frames, ignores duplicates and drive-enabled reports, and never raises;
  - the read-only decoder is checked statically;
  - arbiter drive stays disabled;
  - resolver hardening;
  - udev rule evaluation against the measured properties of all four USB-serial devices.

`build_gcc.sh` also asserts the patched ELF has no SBUS→motion call path.

## 7. Approval gates (each separate; none is approved by this document)

| Gate | What | Hardware state |
|---|---|---|
| **G-0** (owner, now) | SBUS signal wire unplugged and insulated, transmitter off | No power change |
| **B1 Backup** | Stop `rover-base-telemetry` once. Record the PID, steering default angle and car type through the existing getters. Read the full flash (`stm32flash -r` over the board's micro-USB with BOOT0+RESET, or ST-Link SWD) and record the RDP state. Compare the readback with the 3.6.5 hex. | Motor rail at 0 V, motors and steering servo unplugged |
| **G-J** | Install the Jetson patch (dormant), one base restart | E-STOP latched |
| **G-U** | Install the udev proposal and resolver hardening | E-STOP latched |
| **B2 Flash** | Flash the patched image. The restore image is either the B1 readback or the vendor 3.6.5 hex if the readback is impossible. | Same as B1 |
| **B3 Stationary regression** | Version, packet mix (now 5 per encoder cycle), 0 checksum errors, encoder/IMU/battery values, CPU 75% / RAM 80% / 70 °C guards. No motion. | Wheels lifted, E-STOP latched |
| **B4 Isolated SBUS proof** | Motors and steering unplugged, a meter or LED on the motor outputs. Reconnect SBUS, transmitter on with **throttle low**, move every stick. **Expected: zero output.** | Motors disconnected |
| **B5 Live channel test** | CH1–CH10 walk, transmitter-off loss, receiver unplug; Xbox and E-STOP coexistence | FlySky read-only |

**Rollback:**
- Firmware: BOOT0+RESET, then flash the B1 image or the 3.6.5 hex. The STM32 ROM bootloader cannot be erased, so the board is always recoverable.
- Jetson: `rollback.sh <backup>`.
- udev: restore the saved rule.

## 8. Remaining risks

1. ATLAS's exact 3.6.x image is unknown until B1. If the flash is read-protected, restoring means 3.6.5, not the exact factory image.
2. A GCC-built image differs from the vendor's Keil build. B3 must cover IMU init (the firmware halts if the IMU fails), PID behaviour and the steering default.
3. FlySky's SBUS failsafe-flag behaviour on the FS-iA10B is unverified. B5 measures it. Freshness (age) is enforced regardless.
4. If the receiver were reconnected to **factory** firmware by mistake, the direct-drive risk returns. Label the lead.

## 9. Request to Yahboom support (support@yahboom.com)

> Subject: ROS-Driver-Board V3.0 (YB-ERF01) firmware 3.6: source and SBUS behaviour questions
>
> Hello, we run a ROS Robot Expansion Board V3.0 (STM32F103RCT6) as car type 5 (Ackermann, R2). FUNC_VERSION reports 3.6. We downloaded ROS-Driver-Board-FW-master.zip and rosmaster_V3.6.5.hex from your ROSMASTER-A1 Code-Firmware folder (build Aug 29 2025).
> 1. Is 3.6.5 the firmware shipped as "3.6" on boards sold in 2025–2026? If not, could you share the exact hex and source for the version we have?
> 2. Are factory boards shipped with flash read-out protection (RDP) enabled?
> 3. Please confirm that in car type 5, SBUS frames drive Ackerman_Ctrl directly (CH3 throttle, CH1 steering, CH6 brake), regardless of USB host commands. Is there a supported setting to disable SBUS driving without recompiling?
> 4. What happens on SBUS failsafe or loss (FS-iA10B receiver)?
> 5. Is any serial report of RC channels planned or available? We intend to add one locally (function word 0xE1, MCU→host). Please tell us if that conflicts with any reserved function word.
> 6. Which toolchain do you recommend for rebuilding: Keil MDK with ARMCC 5.06?
> Thank you.
