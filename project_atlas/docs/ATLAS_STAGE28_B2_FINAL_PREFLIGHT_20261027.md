# Stage 28 B2 final read-only preflight

2026-10-27. Conditional GO for separately authorized selective programming; no write/erase/unlock performed. Source candidate `5a84be9b12d1d5999bd1dcbb17428f097cc4a589` unchanged.

Owner freshly confirmed Windows USB connection, stable original battery/main-switch ON arrangement, all actuators unplugged, transmitter OFF, receiver board-powered only, Jetson shut down. These physical facts are owner-confirmed, not remotely measured. Owner completed individually guided BOOT0 hold, RESET and BOOT0 release.

## Read-only evidence

CubeProgrammer 2.23.0 connected COM26, UART115200 8E1 flow-off. Chip0x414 high-density F101/F103 family, ROM protocol2.2. Factory capacity halfword read at0x1FFFF7E0 =256KiB. This and owner-marked STM32F103RCT6 are consistent; chip ID alone cannot distinguish every family variant. Tool's displayed512KiB default is not used.

Option-byte display: RDP0xA5 Level0; WRP0–31 unprotected; software watchdog. No option-byte writes. Live page120 SHA256 matches original: `021d16b433f72cfa4d36cd7db607ec4515e6e3195440b32a652cfcd1b3c04195`.

Both original256KiB files still hash `86a436700c56ec682084365711e5303ab9cc738e423fa65e532c4c608ae41a1f`. Candidate BIN hash `8c9c9b3aaa0ae398add3495e5b84e1a54f2f3f3cc3e2e0520e0055b09a733e6c`; HEX `0a03d4bf23355367246116e073455989d2798740d7e9c3c1d79c79353b4eed99`. Build provenance/memory/static tests in preceding offline-build report remain unchanged.

Win32_SerialPort omitted COM26, but present-only Plug-and-Play, .NET serial enumeration and SERIALCOMM registry agreed on CH340 VID1A86/PID7523 COM26. Actual successful ROM reads resolve the inventory discrepancy; no other COM port was opened.

## Proposed future operation — NOT EXECUTED

High-density flash uses2KiB pages: https://www.st.com/resource/en/programming_manual/pm0075-stm32f10xxx-flash-memory-microcontrollers-stmicroelectronics.pdf

Image spans0x08000000–0x0801E01B, requiring pages0–60 inclusive. Erase boundary ends0x0801E7FF. Page60 tail (2020 bytes) was read live and confirmed allFF, matching original backup. Therefore a selective erase of pages0–60 preserves its existing tail state. Pages61–127, including settings page120 at0x0803C000, must remain untouched.

Installed CLI help supports explicit page range erase and --skipErase programming. Future approval must include ONLY the necessary selective erase0–60, exact BIN programming at0x08000000 with automatic erase suppressed, and readback. Never use erase all, unlock or option-byte changes. Do not reset/run firmware automatically.

Readback plan: upload full256KiB after programming; first122908 bytes must equal candidate byte-for-byte and SHA256; all remaining bytes must equal original backup, including page60 tail and settings. Redisplay protection/options and compare unchanged state. Fail on any mismatch; do not automatically retry or restore. Preserve evidence and request a separately scoped recovery action if needed.

Windows recovery: original full-flash files and settings/calibration archive available under work/windows-direct-backup-20261027; ROM UART path just verified. Restoration of original application pages would require separately authorized selective programming/readback. Recovery image exists but an actual restore has not been tested. Jetson remains shut down; no copy-back/service operation is part of this preflight.

## Risks and status

GCC differs from vendor Keil; static stack analysis does not establish runtime worst-case, and physical IMU/encoder/servo behavior remains untested. Supply stability is owner-confirmed; no voltage instrument reading captured. All actuator isolation stays in place through any future firmware validation. Software E-STOP on a shut-down Jetson cannot constrain ROM or board startup, so physical disconnection is essential.

Verdict: preflight PASS / conditional B2 GO for owner decision; execution HOLD awaiting explicit write plus selective-erase authorization. COM26 commands exited; board remains in ROM bootloader, BOOT0 released. Do not press buttons until the next agreed step.

Private evidence: C:/Users/Dhruv/Documents/Codex/2026-07-24/h/work/stage28-b2-preflight-20261027/ (identity/protection, capacity, live settings and tail reads, boundary JSON and SHA256SUMS). Raw diagnostics and backups are not committed.
