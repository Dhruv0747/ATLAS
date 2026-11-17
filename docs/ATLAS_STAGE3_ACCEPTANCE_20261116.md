# Stage 3 — supervised round-trip acceptance result

**Test date:** 16 November 2026  
**Attempt:** 7  
**Recording:** stage3_roundtrip7_us_20261116 (22 topics, including ultrasonic validity)  
**Result:** **NOT ACCEPTED — safe-stop passed; complete route failed.**

## Summary

| Gate | Result | Recorded evidence |
|---|---|---|
| Safe stop | **PASS** | Physical B stop during Nav2 motion at 0.078 m/s; stopped in 0.14 s over 0.006 m |
| Mean moving speed | Observed | 0.144 m/s |
| Dhruv Room → Hall | **FAIL** | Hall goal aborted at the door's right-side no-echo region; owner moved rover into Hall |
| Hall → Dhruv Room | **FAIL** | Owner assistance was needed to get out of Hall |
| Turn-sign | **FAIL** | 1667/103 samples, 5.8% against a 5% limit |
| Encoder health | **FAIL** | One CRITICAL sample while moving |
| Autonomous round trip | **NOT PASSED** | Physical assistance occurred; do not count as autonomous completion |

## Changes and supporting work around the attempt

- Hall named place was moved to a more central point with approximately 1.1 m maximum wall clearance.
- Nav2 progress allowance was increased from 20 s to 45 s; the safety guard was not changed.
- Front/rear ultrasonic coverage was added to the LiDAR availability logic and deployed under the owner's approval.
- The attempt recorded 22 topics, including front/rear ultrasonic validity.
- The dashboard abort path was subsequently owner-verified: autonomy disarmed, Nav2 cancellation acknowledged and the rover-stopped state reported.
- The charger status card and voice/CPU priority work were also recorded on 16 November.

## Important resource finding

A 20-second parked/charging sample showed 371% total CPU across six cores and load average around 19–20. The owner reported CPU reaching 100% during drives and the dashboard becoming unresponsive. The sample is not a drive profile; it establishes a reason to capture per-process CPU, ROS loop rates, TF age, sensor freshness and dashboard latency during the next controlled run.

## Required follow-up

1. Preserve the raw attempt-7 bag and classify remote-assist versus Nav2 command samples before recalculating turn-sign.
2. Diagnose the right-side Hall door no-echo region using recorded LiDAR, Astra and ultrasonic evidence. Do not convert missing returns into free space.
3. Investigate the single encoder CRITICAL sample using raw per-wheel counts and packet age.
4. Repeat the supervised route with a fresh recording and no physical assistance.
5. Require all route, encoder, turn-sign, localization and safe-stop gates to pass before declaring Stage 3 complete.

## Provenance

The detailed source is the 16 November entry in [ATLAS_CURRENT_BLOCKERS.md](https://github.com/Dhruv0747/ATLAS/blob/claude/jetson-live-snapshot-20261106/docs/audits/ATLAS_CURRENT_BLOCKERS.md). This summary preserves its failed gates rather than presenting the safe-stop PASS as a complete autonomy PASS.

No additional motion or deployment is authorized by this document.
