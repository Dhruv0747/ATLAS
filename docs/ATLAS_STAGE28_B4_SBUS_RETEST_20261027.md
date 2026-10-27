# Stage 28 B4 S.BUS retest — partial validation

One authorized passive Windows COM26 session; no retry. Firmware identity V3.6.161 derives from prior verified boot/programming evidence. Owner confirmed actuators disconnected and Jetson shut down. Transmitter is now OFF per owner.

## Verified evidence

- 900.004 seconds; automatic TIME_LIMIT; serial port closed; zero serial writes.
- 109,762 valid protocol packets and 21,952 RC reports containing decoded channel values. This is NOT a count of all receiver SBUS frames; telemetry sequence is wrapping/decimated.
- Direct-drive-disabled flag true in every RC report. No monitor abort for checksum, framing, stale RC stream or nonzero motion telemetry. This does not measure electrical actuator outputs.
- Initial transmitter OFF: fresh receiver frames with failsafe=true and frame_lost=true, all ten channels 1024. After ON, both flags cleared. Freshness alone does not establish a usable radio link.
- Final OFF transition was NOT captured: logger expired before that transition appeared. Final saved flags remained clear. Signal-loss transition timing and final failsafe response remain unverified. No automatic reopening/retry performed.

| Channel | Observed deliberate mapping |
|---|---|
| CH1 | Right stick horizontal: left 240, centre 1024, right 1807 |
| CH2 | Right stick vertical: down 240, centre 1024, up 1807 |
| CH3 | Left stick vertical: up 1807, centre 1024; down endpoint not tested |
| CH4 | Left stick horizontal: left 240, centre 1024, right 1807 |
| CH5–CH10 | 1024 observed; switch/knob mapping and range untested |

Held endpoints were checked across approximately three seconds of fresh reports. All ten channels repeatedly returned to 1024 at hands-off centre. Other stick axes varied during some holds; diagonal hand movement versus mixing is not determined. Do not infer a hardware fault or assign untested controls.

## Result and remaining gate

PASS for decoded S.BUS delivery and the listed channel observations; overall ten-channel/failsafe validation INCOMPLETE. Changing transmitter serial mode from i-BUS to S.BUS preceded successful decoded delivery, without a firmware change. Do not enable drive control. A separately approved bounded session is needed for CH3 down, CH5–CH10 assignments, and a captured ON-to-OFF failsafe transition. Reserve time for signal loss before other channel work.

## Evidence and integrity

Local evidence: `C:\Users\Dhruv\Documents\Codex\2026-07-24\h\work\stage28-b4-sbus-mode-retest-20261027`

Raw stream SHA256: `bafd5bbf0c1d000521cb9ab2a6dbf163c4d2e1f3323be3f55fb7d1020cef0860`

`session-summary.json`, numbered immutable status snapshots, action observations, reports.jsonl, raw.bin and SHA256SUMS retained locally. Raw telemetry is not committed. Hash manifest generated and verified after capture closed. No production configuration, firmware, steering or safety policy changed.
