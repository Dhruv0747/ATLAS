# Stage28 direct Windows original firmware backup — COMPLETED AND VERIFIED

2026-10-27 owner authorized Windows USB/CH340 read-only backup, with separate B2 gate. Jetson configuration/calibration and last-hour user journal copied to Windows and SHA256 verified before authorized orderly shutdown. Owner confirmed shutdown complete, moved board USB to Windows, and confirmed original battery/main-switch-ON arrangement, actuators unplugged, transmitter OFF and receiver powered only by SBUS. Software E-STOP was latched before shutdown; it cannot protect a board disconnected from the stopped Jetson, so physical isolation remains essential.

Windows STM32CubeProgrammer2.23.0 verified with --help. CH340 COM26 VID1A86/PID7523 detected; exclusive-open check sent no bytes and released port. Owner followed BOOT0-hold, RESET press/release, BOOT0-release individually. UART115200,8E1,flow OFF connected successfully.

Verified chip0x414 STM32F101/F103 high-density family. Factory capacity halfword0x1FFFF7E0 read00 01 =256KB, matching owner-confirmed F103RCT6. CubeProgrammer512KB is explicitly a default and was not used. Display-only option-byte operation reports RDP0xA5 Level0/no protection; raw16 option bytes archived. No write/erase/unlock/protection command executed.

Two independent full-flash uploads from0x08000000,262144 bytes each completed successfully in34.120s and34.149s. Byte-for-byte identical and SHA256:
`86a436700c56ec682084365711e5303ab9cc738e423fa65e532c4c608ae41a1f`.
Initial SP0x20006260 within48KB RAM; reset vector0x080001e1 in flash/Thumb. Nontrivial image content. Full original settings included, page120 separately extracted (offset0x3c000,length2048). Matching images establish readback consistency, not a tested flash restoration.

Windows private evidence directory:
`C:/Users/Dhruv/Documents/Codex/2026-07-24/h/work/windows-direct-backup-20261027/mcu/`
Includes flash-pass1.bin,flash-pass2.bin,flash-size.bin,option-bytes-readonly.bin,settings-page120.bin,verification.json,SHA256.json and command logs. Jetson calibration/configuration archive is in parent directory. No firmware/private raw evidence committed to Git. Copying original firmware back to Jetson awaits restoration of the owner-guided USB/power arrangement.

## Modified firmware readiness: NO-GO for B2

Existing reviewed source patch retains ENABLE_SBUS_DRIVE0 and ENABLE_SBUS_REPORT1; previous reports cover motor/encoder/IMU preservation and GCC compatibility fixes. However, no exact built modified binary/build provenance artifact was located in current repository/workspace/WSL locations searched. A hash-verified final artifact and build audit are still required; do not treat source inspection or historical report as current binary verification. GCC image differs from vendor ARMCC and requires separately authorized stationary regressions. Original recovery image now available, but no writing authorized.

COM26 was released after reads. Owner was asked to perform normal RESET with BOOT0 released; confirmation and subsequent USB return/Jetson telemetry verification are pending at report time. Do not reconnect actuators or turn transmitter on. No automatic flashing or host-side MCU GO command. Profiler missing-/usr/bin/time issue stays separate and did not block this backup.
