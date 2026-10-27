# Stage 28 B4 signal-first session and CH5 diagnosis — 2026-10-27

## Captured results
One approved 900-second passive session, no retry. COM26 closed at TIME_LIMIT, zero serial writes, 109763 packets, 21953 decoded RC reports. Direct-drive-disabled true throughout. Owner reports transmitter OFF and actuators disconnected. Final OFF was after capture expiry; do not claim its flags were measured.

The earlier deliberate ON-to-OFF transition WAS captured: frame_lost at monotonic 550037.5961518, failsafe at 550038.0879576 (0.4918058 seconds between observed flags, NOT switch-to-failsafe latency). Both flags subsequently cleared after ON. Reports remained fresh during failsafe: freshness must never override failsafe.

CH3 DOWN = 240 across 73 reports; centre subsequently all channels 1024. Previous session established CH3 UP = 1807. CH4 also deflected during DOWN hold; hand motion versus mixing remains undetermined.

CH5-CH10 stayed exactly 1024 throughout this session. Owner initially found all six Nul, then reported CH5 SWx/SwA. Neither reported SwA movement nor leaving the assignment menu changed the received CH5 value. CH6-CH10 assignments were not changed or validated.

## Diagnosis and limitations
Independent bit-by-bit extraction from 19219 raw checksum-valid RC packets confirms centred auxiliary channels, excluding a display-only explanation. Firmware patch SBUS_Send_Report copies the received frame under interrupt exclusion; SBUS_Build_Report copies all 23 payload bytes unchanged. There is no four-channel-only restriction in this reporting path.

31 existing FlySky core unittest tests PASS. 18 isolated synthetic report/parser roundtrips PASS (CH5-CH10 independently at 240/1024/1807, others unchanged). These validate PC decoding, not radio hardware. Pytest report suite was not run: pytest is unavailable in current Windows Python; no dependency installation performed.

Exact CH5 cause remains UNPROVEN. Candidate causes include transmitter output configuration (assignment/model, endpoints/mix/fly-mode override), physical switch identification/input, or radio/receiver output. Do not assert an encoder, MCU, receiver or switch defect. No firmware correction justified yet.

Single next discriminating observation: on a separately supervised transmitter check, inspect the transmitter's own Display Servos CH5 bar while toggling the labelled SwA. FlySky manual says swipe right from home for real-time channel display. Do NOT long-press: that activates channel sweep. If CH5 stays centred there, inspect active model, assignment, endpoints and fly-mode/mix settings without blindly changing them. If it moves there, investigate downstream radio/receiver/SBUS path; a new PC capture requires separate approval. Keep transmitter OFF now, no further live session started.

Manual: https://static.rapidonline.com/downloads/airgineers/fs-i6s.pdf sections 5.5, 6.7.

## Evidence
Local directory: C:/Users/Dhruv/Documents/Codex/2026-07-24/h/work/stage28-b4-signal-first-20261027
Raw SHA256: 68360207f12d781ba9274415ed3de9039296630224ace794d155f63b102d8234
final-summary.json, signal-loss-observation.json, independent-bit-decoding.json, numbered snapshots and action observations preserved; SHA256SUMS generated and reverified after closure. Raw evidence stays local.
No flashing, reset, motor commands, production changes or drive enablement. Signal-loss reporting and CH3 endpoint PASS; auxiliary-channel mapping INCOMPLETE.
