# Stage 28: original-firmware backup through SWD

2026-10-27. Offline investigation only, continuing 7e3c4dc. No Jetson command, MCU connection, reset, halt, service change or firmware operation was performed in this investigation. Windows CubeProgrammer was invoked with `--help` only.

## Recommendation

Prefer a genuine ST-LINK/V2 with documented target-voltage sensing, using SWD HOTPLUG for a separately approved, supervised read-only attempt. This avoids the UART port-ownership conflict and normally avoids BOOT0/RESET. **Conditional GO for preparation; NO-GO for hardware execution now.** Probe identity, actual header orientation, target voltage and future approval remain gates. Successful live access and uninterrupted telemetry are not yet demonstrated.

The 7e3c4dc finding remains valid: atlas-sensor-recovery restarted the intentionally stopped base driver and reclaimed ttyUSB0. The attempted UART backup read no flash. Later owner power/reset restored LIVE packets with the same host PID. Neither an original flash image nor the MCU's read-protection state is available yet.

## J16 schematic verification and wiring

Visually inspected Yahboom `ROS-ExpansionboardV3.0-en-new-20250509.pdf`, SWD block. Manufacturer download is linked from https://www.yahboom.net/study/ROS-Driver-Board/ under Hardware Info / SCH of expansion board; file ID `1sC3g9Bo_lSMDfegUk3m6Bi2menp2mgz-`.

| J16 schematic pin | Signal | Genuine ST-LINK/V2 CN3 20-pin connector |
|---|---|---|
| 1 | +3.3 V target rail | Pin 1 VAPP / target voltage reference INPUT |
| 2 | SWCLK | Pin 9 TCK_SWCLK |
| 3 | GND | Pin 4 GND |
| 4 | SWDIO | Pin 7 TMS_SWDIO |
| 5 | Ground symbol | Not needed when pin 3 provides common ground |

```text
Windows USB ---- genuine ST-LINK/V2       Yahboom J16
                 VAPP input (CN3 1) <---- pin 1 +3.3 V
                 SWCLK      (CN3 9) ---- pin 2 SWCLK
                 GND        (CN3 4) ---- pin 3 GND
                 SWDIO      (CN3 7) <--> pin 4 SWDIO
                 NRST       (CN3 15)     NOT CONNECTED (absent at J16)
                 power output / 5 V     NOT CONNECTED
```

This is a signal diagram, NOT a left-to-right photograph of the physical connector. The schematic labels the symbol `XH2.54-4P` despite showing five numbered connections. Confirm the fitted connector, pin-1 marking and continuity before choosing a cable; do not infer physical orientation or a fifth accessible contact from this drawing. No continuity test is authorized now.

Never connect an ST-Link clone's pin labelled `3.3V` without verifying its function: many clones expose a power OUTPUT rather than VAPP. Do not parallel that output with the powered board rail. Keep the board's established supply; the probe senses it, not powers it. Use short secured leads and a correctly matched adapter, not loose live probing. Wiring attachment needs a separate safe connection plan; software HOTPLUG does not mean physically hot-wiring is safe.

Required hardware: genuine ST-LINK/V2 (or an equivalently documented ST probe with genuine VTref input), Windows USB data cable, CN3-to-J16 signal adapter matched to the actual fitted connector, four short insulated leads, and a meter for voltage/continuity verification under an approved wiring plan. A generic CH340 USB-UART adapter cannot perform SWD. A clone's layout is not interchangeable with the CN3 numbering above.

## Can factory firmware stay running?

ST's CubeProgrammer 2.23 documentation specifies HOTPLUG attachment without halt or reset. Explicitly select it; NORMAL is the default and is not the approved mode. J16 lacks NRST, so hardware connect-under-reset is unavailable through this header. Do not substitute a software reset, halt, BOOT0 sequence or add an NRST wire if hot-plug fails.

The hash-verified published 3.6.5 source (`3d7a6e1c762bdd42dad81468cd34d6907847ab8ebb03abb16024d888a4f0687e`, source zip) calls `Bsp_JTAG_Set(SWD_ENABLE)` in `Source/BSP/bsp.c:349`; its implementation configures AFIO_MAPR to preserve SWD. This supports feasibility, but the exact installed 3.6.x binary is still unknown. Actual RDP, debug availability and firmware behavior must be established without changing them.

SWD debugger attachment changes debug-access state even when flash is read-only. Memory-bus contention, signal integrity, ground paths, probe behavior, protection faults or firmware settings can still disrupt execution. RDP can prevent reading and interfere with execution under debug: do not promise a nondisruptive connection on a protected target. If the program, telemetry or target state changes, stop/disconnect the probe; do not automatically reset, resume or reconnect. Recovery may then need a separate owner-approved action.

## Read protection

STM32F1 PM0075: unprotected RDP code is 0xA5; changing protected to unprotected mass-erases main flash. RDP protection blocks external flash extraction through SWD and the ROM UART route. **No unlock/unprotect, option-byte write, erase or protection regression is permitted.** Do not apply newer-family RDP encodings blindly to this STM32F103.

Read/display option bytes if permitted; access denial is not proof of RDP by itself (wiring, voltage, debug availability or tool connection can also fail). If protection cannot be established safely, stop and report unknown. Do not interpret an all-FF/zero output file as a valid backup just because two hashes match.

## Proposed read-only software procedure — NOT executed

1. Separate approval must cover physical probe attachment and ONE SWD HOTPLUG backup session with explicit stop conditions. Maintain actuator disconnection, transmitter OFF, E-STOP, existing main-switch-ON/battery arrangement and protected services. Verify live packet progression/age and zero commands before attach. Keep BOOT0 in normal boot state.
2. Verify exact probe model, wiring, target 3.3 V reference and serial number. Use installed CubeProgrammer 2.23.0. No external flash loader, target power control, automatic programming or firmware upgrade. Close other probe clients.
3. In CubeProgrammer select ST-LINK, SWD, HOTPLUG and a supported low SWD clock (100 kHz if offered by the selected probe). Do not select NORMAL or Under Reset. Connect once; record log, chip identity and protection display. Abort on unexpected reset/halt, denial, error, unstable voltage or telemetry degradation. No fallback mode or retry.
4. Read factory flash-size halfword at 0x1FFFF7E0; expected RC capacity is 256 KB. Verify chip/size consistency before determining length. Read option bytes without Apply. Capture UID if readable. If identification is inconsistent or inaccessible, stop rather than guessing.
5. Only after unprotected 256 KB identity is established, read 0x08000000 through 0x0803FFFF twice into separate files, 262144 bytes each. Sequential read operations in the existing GUI HOTPLUG connection avoid repeated connections. Save data from Memory/File edition; do not use Download/Programming.
6. Approved-command equivalents for a future reviewed CLI session are below. They are reference examples, not an authorization or a script to run now. Every CLI invocation creates a connection; explicitly retain HOTPLUG and the verified probe serial each time. Stop between phases to review results; do not paste all commands unattended.

```powershell
$cp = 'C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe'
# <VERIFIED_PROBE_SERIAL> is intentionally not filled in.
& $cp -c port=SWD mode=HOTPLUG freq=100 'sn=REPLACE_WITH_VERIFIED_PROBE_SERIAL' -ob displ
& $cp -c port=SWD mode=HOTPLUG freq=100 'sn=REPLACE_WITH_VERIFIED_PROBE_SERIAL' -u 0x1FFFF7E0 2 flash_size.bin
# Only after chip/size/protection checks pass:
& $cp -c port=SWD mode=HOTPLUG freq=100 'sn=REPLACE_WITH_VERIFIED_PROBE_SERIAL' -u 0x08000000 262144 flash_pass1.bin
& $cp -c port=SWD mode=HOTPLUG freq=100 'sn=REPLACE_WITH_VERIFIED_PROBE_SERIAL' -u 0x08000000 262144 flash_pass2.bin
Get-FileHash flash_pass1.bin, flash_pass2.bin -Algorithm SHA256
```

7. Require exact file lengths, equal SHA256 AND byte comparison, plausible vector table and content, no read errors, and consistency with the identified device. Full flash includes settings page 120 at offset 0x3C000 (2048 bytes); extract it offline and use the existing settings decoder. Preserve option bytes separately as evidence, never as an automatically restorable write recipe. A mismatch may reflect a settings write while running; do not halt or retry automatically to force equality.
8. Preserve host calibration separately. Copy both flash passes, decoded settings, identity/protection logs and manifest to Windows and Jetson; recheck hashes on each destination. Disconnect in software without reset/halt/start. Verify packet counts continue increasing, age returns to baseline, no new stale/checksum errors, same service identities and safe control policy. Matching files alone do not prove a validated restore path.

Forbidden operations include write/download, erase, read-unprotect, option-byte assignments, unlock, power control, halt/step, reset, start/GO, test firmware, external loader and any B2 continuation.

## Telemetry and recovery interaction

SWD does not need ttyUSB0, so there is no inherent reason to stop rover-base-telemetry for a HOTPLUG read. Existing USB telemetry can remain running and provide independent health evidence. But if SWD causes stale data, atlas-sensor-recovery could again restart the base; that risk remains. Future live approval must define a bounded maintenance policy for the base recovery trigger, preserving fault reporting, E-STOP and other safety checks. Do not silently disable the recovery service. The offline gate in 7e3c4dc applies to UART B1; it is not automatically a SWD execution policy.

## Software-only capability review

Inspected all request/command switch handlers in hash-verified 3.6.5 `Source/APP/protocol.c` and the associated header. They provide version, reporting, motor/servo/PID/car-type controls and selected settings; no arbitrary-address full-flash read/upload API is present. `FUNC_RESET_FLASH` resets settings and is destructive, not a backup command. Exact installed firmware remains unknown, so this is 'no supported capability found in published source', not proof about every undocumented factory build. Adding a flash-read handler would require replacing the firmware before backing it up and does not solve this task. Do not probe undocumented commands or use exploits.

## Comparison

| Aspect | SWD HOTPLUG | ROM UART B1 |
|---|---|---|
| Additional hardware | Verified ST-Link and safe adapter | Existing CH340 USB path |
| BOOT0/reset | Normally unnecessary | Physical entry and normal reset required |
| Base telemetry | Can remain active; must validate actual timing | Must relinquish serial port |
| Known ATLAS failure | Not yet tried | Recovery service reclaimed port |
| RDP-protected flash | Cannot extract without forbidden destructive unprotect | Same limitation |
| Failure recovery | No NRST on J16; stop if hot-plug fails | Physical reset/boot pins required |
| Main risk | Wiring/debug side effects, timing disturbance | Maintenance race, telemetry outage, physical mode transitions |

Safest next step: identify the exact probe and physical J16 orientation, then review a single HOTPLUG read-only attempt and maintenance/abort policy. Do not buy an unspecified V2 clone on the assumption that its 3.3 V pin is a reference input. **No hardware action is approved by this report; B1/B2 remain stopped.**

## Primary references and validation

- ST CubeProgrammer 2.23: https://dev.st.com/stm32cube-docs/prog/2.23.0/en/docs/markup/CubeProg_Command_Lines.html (HOTPLUG, upload, display-only options); installed CLI help independently checked.
- ST ST-LINK/V2 UM1075: https://www.st.com/resource/en/user_manual/um1075-stsw-link007.pdf (CN3 pin mapping and VAPP).
- ST STM32F1 PM0075: https://www.st.com/resource/en/programming_manual/pm0075-stm32f10xxx-flash-memory-microcontrollers-stmicroelectronics.pdf (read protection and destructive unprotection).
- Yahboom hardware: https://drive.google.com/file/d/1sC3g9Bo_lSMDfegUk3m6Bi2menp2mgz-/view (J16 visual check).
- Preserved prior failure/recovery report: ATLAS_B1_ABORT_AND_RECOVERY_20261027.md, commit 7e3c4dc.

Validation is documentation/source/CLI-help inspection only. No hardware-read, timing or backup-success test is claimed. No production files or services changed.
