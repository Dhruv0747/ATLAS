# ATLAS controlled rollout — 2026-10-11

Owner directive: staged diagnostic/reliability deployment while stopped and
latched; no motor, steering, autonomy, map, calibration or network authority
changes. Dedicated branch: `agent/sync-developer-20261011`; never merge main.

## Reconciliation

Fetched developer branch `claude/localization-motion-investigation`: `248d42c`
is included in baseline `b8945a8`. Existing stages 1, 1b, 2, 3, 4 and 5 are
already deployed; do not redeploy them. Their records and rollback paths remain
in `docs/deploy/`. Owner reports V2 E-STOP, PIN reset/release and manual driving
worked: **operator-observed functional checks**, not formal edge-case passes.
Remaining edge cases are grouped in the existing stage-1 on-device procedure.

## Recorder

Background writer: 32 MiB / 30,000-message queue, ordered single worker, no
control publications. Atomic pre-roll enqueue; full disk, overflow and storage
quota errors stop recording, never robot control. No old evidence is deleted.
Per-root lock prevents two writers owning one retention directory. No service
is installed. `--duration` supports finite trials; `--stationary-probe` triggers
only the recorder after checking fresh latched stop, zero command and inactive
Nav2/exploration. It does not command movement.

Fifteen offline tests pass: startup, missing sensors, repeated short motion,
pre/post timing, timestamps, storage limits, blocked disk, overflow, failed disk,
ordered multiple captures, pending-write shutdown and restart. Abrupt kill can
leave an incomplete bag; it is preserved, not silently repaired/deleted.

Actual Humble pre-roll transfer (7,874 samples): 37.07, 5.62, 5.23 ms versus
463–512 ms previously. Intermediate per-message locking was slower and rejected
in favour of one bounded batch. Final 60-second Humble test: 47,887 samples,
two bags, 25 topics, identical timestamp/payload/order hashes, SQLite integrity
OK, zero application drops and zero pacing ticks over 100 ms. CPU 16.57% of
one core, recording RSS 63.59 MiB, process peak 68.02 MiB, bag allocation
19,718,144 bytes. Whole-NVMe writes 34,996,224 bytes include other processes;
per-process I/O counters unavailable. Free storage 396.50 GB. Parked live
measurements still required.

DDS loss callbacks report only middleware-reported loss, not proof of zero
upstream loss. Serialized header stamps remain unchanged; bag timestamps are
ROS receipt time. Latched TF context uses capture-start bag time, as in the
existing recorder. Normal ring expiry is counted separately from actual drops.

## Connectivity baseline

120-second parked observation: gateway 24/24 replies, median 1.545 ms, p95
2.01 ms, max 2.52 ms; no observed Wi-Fi disconnect, DHCP failure or route flip.
Localhost dashboard 24/24, median 72.75 ms, max 137.44 ms (not network RTT).
Separate PC HTTP requests: LAN 10/10, mean 132.44 ms, max 309.26 ms; Tailscale
10/10, mean 196.78 ms, max 447.19 ms. Small samples, not endurance proof.

BMS: 15 connect-stage timeouts / 120 s, no healthy samples. No bonding failures
in that window. Historical bonding errors do not prove these connect timeouts
have the same cause. Current radio power save ON, regulatory domain 00
(self-managed driver); existing main-router/secondary-AP DHCP findings stand.
No network settings changed; no before/after network-change benefit claimed.

## Pending gates

- Recorder stage install + rollback rehearsal, parked finite capture/resource check.
- Separately tested BMS healthy-link reuse and bounded reconnect backoff.
  Preserve five-second healthy polling: lifted commissioning has a ten-second
  freshness maximum. Do not simply change safety polling to 15 seconds.
- Wi-Fi power-save A/B needs exact backup, timed rollback, independent access
  and owner approval. No router/BSSID, regulatory domain or routing changes yet.
- LiDAR supply hypothesis unproved; startup power measurement needed.
- Wheel scale, yaw/IMU agreement and moving localization remain unresolved;
  no retuning/reseeding. Accepted map preserved; remapping needs supervision.
- PID, camera VO, semantic-navigation and Whisper remain gated proposals/evaluation.

Do not drive until a fresh READY and a supervised manual test is coordinated.
