# Stage 28 B2 selective programming — PASS

2026-10-27, verification 16:33:20 IST. Owner explicitly authorized one selective erase pages0–60 and one exact BIN write, with no reset. Owner freshly reconfirmed disconnected actuators, transmitter OFF, stable board power, Windows USB and no competing serial application.

## Preflight

Candidate source `5a84be9b12d1d5999bd1dcbb17428f097cc4a589`; approved preflight/report revision `012faa632fd6fd459ead89128bc6e3a2b3542a70`. Clean worktree at execution. Exact BIN SHA256 `8c9c9b3aaa0ae398add3495e5b84e1a54f2f3f3cc3e2e0520e0055b09a733e6c`.

Both original256KiB backups accessible and hash `86a436700c56ec682084365711e5303ab9cc738e423fa65e532c4c608ae41a1f`. Fresh complete pre-flash read matched that hash. COM26 CH340 VID1A86/PID7523 present/OK; CubeProgrammer2.23.0 obtained exclusive serial connection, UART115200 8E1 flow OFF. Chip0x414, factory capacity256KiB, RDP0xA5 Level0, all32 WRP fields unprotected. Tool512KiB default was ignored.

## Executed sequence

1. Read-only option display, capacity and full pre-flash upload.
2. Exactly one `-e '[0 60]'` selective erase, successful.
3. Exactly one `--skipErase -w <approved fw.bin> 0x08000000`, successful in18.587seconds. No automatic erase or retries.
4. Full262144-byte upload and offline byte-by-byte verification against candidate followed by original remaining bytes.
5. Read-only option display; all38 parsed RDP/user/data/WRP fields identical to preflight.

No mass erase, read-unprotect, option write, MCU GO/reset, motor command, actuator reconnection or Jetson operation occurred.

## Verification

- Programmed122908-byte region byte-identical to candidate; SHA256 `8c9c9b3aaa0ae398add3495e5b84e1a54f2f3f3cc3e2e0520e0055b09a733e6c`.
- Every byte after the image unchanged, including erased-page60 unused tail and untouched pages61–127.
- Settings page120 SHA256 unchanged: `021d16b433f72cfa4d36cd7db607ec4515e6e3195440b32a652cfcd1b3c04195`.
- Full post-flash SHA256: `3429f94465f758215e068545b00883885f4c280a14d3dd2e5430511e51c4ecfb`.
- Protection and option fields unchanged.

Private evidence directory: `C:/Users/Dhruv/Documents/Codex/2026-07-24/h/work/stage28-b2-write-20261027/`. Contains complete CLI outputs, durable single-attempt markers, before/after full-flash images, capacity, region/settings extracts, verification script/JSON and SHA256SUMS. Original backups remain in windows-direct-backup-20261027/mcu. Raw backups/logs are not committed.

## Stopped state and next gate

CLI exited and released COM26; board left in ROM bootloader with BOOT0 released. Programming PASS is not a runtime or hardware-function PASS. GCC behavior, live telemetry and peripheral regressions remain untested. Physical actuator isolation remains essential; Jetson is shut down, so its software stop is not active board enforcement.

Request separate permission for one owner-guided normal RESET and passive stationary serial validation with all actuators disconnected and transmitter OFF. No Jetson deployment, motor/steering test, automatic recovery write or actuator reconnection is included. Original recovery image remains available, but actual restoration has not been exercised.
