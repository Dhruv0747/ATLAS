# Stage 28 modified firmware: reproducible offline candidate

2026-10-27. Offline build PASS; B2 writing remains **HOLD / NO-GO** pending the remaining compatibility review and a fresh owner confirmation. No serial port, MCU flash, board reset, Jetson service or actuator was accessed in this build task.

## Provenance and changes

Starting repository commit: `90e2bb0e08646429811534a907195e0e52c02b0f`, branch `agent/stage28-b1-safety-resolution`. Existing RC and GCC compatibility patches recovered from revision `c539ae5`; those patches were not changed in this task. Vendor source ZIP SHA256: `3d7a6e1c762bdd42dad81468cd34d6907847ab8ebb03abb16024d888a4f0687e`. Vendor 3.6.5 reference HEX SHA256: `088af51933e98e51105412a0dbf4f5d078dbc3bcff7664105a094d073e12b55b`. Matching these artifacts does not establish source-to-vendor-binary equivalence across compilers.

Owner-approved PC WSL Ubuntu 22.04 installation: gcc-arm-none-eabi `15:10.3-2021.07-4`, compiler `10.3.1 20210621`, Newlib `3.3.0-1.3`. Keil ARMCC was unavailable. Build targets Cortex-M3 Thumb, STM32F10X_HD, 256 KiB flash / 48 KiB RAM. FreeRTOS pinned to `628059b775ba7e0e5d7492291035c6f7c9870be5`; CMSIS F1 pinned to `c8e9a4a4f16b6d2cb2a2083cbe5161025280fb22`.

Changes:
- Makefile.gcc: rename vendor `pid_t` to `atlas_pid_t` only in staging, for both pristine and patched builds, to avoid Newlib type collision. Force `_printf_float` linkage to preserve OLED voltage/IMU float formatting.
- build_gcc.sh: verify vendor hashes; pin/verify dependency commits; fixed SOURCE_DATE_EPOCH/TZ/locale; emit BIN as well as HEX.
- .gitattributes: LF for shell scripts and Makefile.
- verify_release_image.py: independent offline Intel HEX checksum, application-boundary, vector and BIN equivalence verification.
- test_stage28_release_image.py: corruption/boundary/vector rejection and build-policy tests.

## Exact candidate artifacts

Windows directory: `C:/Users/Dhruv/Documents/Codex/2026-07-24/h/work/stage28-b2-final-20261027/`.

| File | SHA256 |
|---|---|
| fw.bin | `8c9c9b3aaa0ae398add3495e5b84e1a54f2f3f3cc3e2e0520e0055b09a733e6c` |
| fw.hex | `0a03d4bf23355367246116e073455989d2798740d7e9c3c1d79c79353b4eed99` |

ELF, linker map, two final build logs, build-sources.tar.gz and SHA256SUMS retained alongside these files outside Git. Earlier non-float images are superseded and must not be flashed.

Final BIN span 122,908 bytes, 0x08000000–0x0801E01B. ELF text 122,104, initialized data 788, BSS 28,472 bytes. Flash sections total 122,892 bytes (BIN includes alignment); static RAM 29,260 / 49,152 bytes, leaving 19,892 bytes outside static allocations. BSS includes the configured FreeRTOS heap; this is not a measurement of runtime stack/heap high-water marks. Initial SP 0x2000C000, Thumb reset vector 0x08018AD9.

## Validation results

- Two clean final builds produced byte-identical BIN and HEX.
- 32 focused pytest tests passed: RC packet/flags/checksum and all 16 channels (including the required 10), host publish-only hooks, drive-disabled rejection, release-image validation and build constraints.
- Independent HEX parser: all record checksums, EOF, address boundaries, vectors and exact BIN equivalence PASS.
- Compiled-image audit: IRQ vector equivalence to vendor reference, six nonkernel interrupt handlers without detected FreeRTOS calls, three SBUS functions without detected motion/motor/steering call paths PASS.
- Seven task static direct-call stack estimates within configured stack sizes, including float-formatting OLED path (1,168 bytes + 64-byte context versus 2,048 allocated). Static analysis cannot prove indirect/library or asynchronous worst-case stack usage.
- ENABLE_SBUS_DRIVE=0; ENABLE_SBUS_REPORT=1. Firmware version marker 3.6.0xA1. Motor, encoder, IMU, battery, steering and flash source implementations remain unchanged by RC patches; app task-stack/heap/OLED compatibility changes are explicit. Changed Source files versus pristine are app.c, app_oled.c, app_sbus.c/h, config.h, protocol.h and bsp.h. Preservation at source level is not hardware validation.

## Settings and recovery

Both existing 262,144-byte original backups were rehashed locally and match `86a436700c56ec682084365711e5303ab9cc738e423fa65e532c4c608ae41a1f`. No new physical backup was performed. Originals and extracted settings page are in `work/windows-direct-backup-20261027/mcu/`; Jetson calibration/configuration archive remains in its parent.

Candidate contains no bytes at settings page 120, 0x0803C000. Any future writer must use reviewed selective page erase/programming only, never mass erase or unlock; preserve all bytes outside the application update range, particularly settings. Existing firmware startup initialization may still write settings under its original conditions; no unconditional preservation claim is made solely from HEX boundaries. Actual restore execution remains untested. Original firmware copy back to Jetson is still pending because Jetson remains shut down; do not restart it for this task.

## Remaining gates and verdict

**Offline candidate: GO for owner review; actual write: HOLD until confirmation and fresh hardware gates.** The missing compiler/artifact blocker is resolved. GCC is not binary-equivalent to the vendor Keil image; hardware behavior remains to be validated with actuators isolated.

Compiler warning disposition completed without silently changing vendor IMU logic:
- `dmp_read_fifo` has an uninitialized return only for zero length. Source search found one call in `dmp_get_fifo_all`; it explicitly returns when `in_fifo == 0` before calling. Thus the current call path excludes the warned case. Future callers must preserve that precondition.
- SBUS `sbus_start & sbus_buf_index >= ...` parses as `sbus_start & (sbus_buf_index >= ...)`; sbus_start is assigned 0/1, so the warning does not change this comparison's truth value. Existing packet regressions cover reporting.
- `_write` passes null FILE to the vendor `fputc`, which does not dereference FILE and directly transmits USART bytes; the final ELF resolves to that vendor implementation. This remains a hardware-dependent retarget, not a general libc substitute.
- M_PI is the existing vendor float constant; no new numeric tuning was introduced.
- Existing pedometer debug `%d` uses unsigned long; on this target both are 32 bits, but high values can display signed. It does not alter IMU computation or control and remains a vendor diagnostic limitation.
- Pristine OLED overflow warnings are addressed in the existing patched 24-byte date/version buffer. Final patched logs remain available; this is not a warning-free build claim.

Fresh MCU identity/capacity/protection and physical isolation checks are required in the future supervised hardware session. Offline checks cannot prove live UART, IMU timing, encoder or steering behavior; stationary regression is a separate post-write gate with actuators still disconnected. Direct FlySky actuation remains prohibited.

Next approval: confirm this exact BIN/HEX pair for ONE supervised selective application write and readback verification, conditional on fresh MCU identity/protection and verified preservation of settings. No mass erase, unlock, read-protection change, actuator connection or Jetson deployment is included. Give BOOT0/RESET instructions individually only after that confirmation. If the programming tool cannot guarantee the reviewed selective range or any preflight fails, do not write.