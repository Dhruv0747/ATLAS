# ATLAS controlled rollout — 2026-10-11

Later owner-approved deployment supersedes this report's pending/rollback
state: see `ATLAS_MASTER_DEPLOYMENT_2026-10-11.md`. Preserve this earlier
report as the record of unsuccessful stages and their rollback evidence.

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

First parked subscriber trial failed: Humble exports SubscriptionEventCallbacks
from `rclpy.qos_event`, not `rclpy.event_handler`. The writer test did not exercise
live discovery. Preserve `live_parked` evidence; rollback this stage before the
corrected install. READY now waits for required topics instead of falsely
declaring readiness with no subscriptions. Regression covers the Humble import.

- Recorder install, rollback rehearsal and parked finite capture completed below.
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

## Completed installation evidence

Stage 6 initially installed `539ca0f`, then rolled back after the subscriber
failure; all evidence retained. Corrected stage 6b installed recorder commit
`0c1d520` at 16:01 IST. Files: `scripts/atlas_motion_recorder.py`,
`scripts/atlas_motion_recorder_core.py`, `scripts/atlas_motion_recorder_writer.py`.
Their SHA-256 prefixes: `02fcaed2`, `c12a735a`, `3ca1adb5`. Scratch installation,
exact hashes and byte-identical rollback passed before live installation.

Parked live trial: READY -> RECORDING -> READY -> STOPPED; 3,203 messages in
one 20.67-second bag, 19 active topics; SQLite integrity OK. All 25 allowlisted
topics subscribed; idle command sources need not publish. No missing/stale
required topics at final observation, no application queue drops or writer
errors. DDS reported **one** lost message; transport is not certified lossless.
Peak queue 642,564 bytes / 1,378 messages, fully drained. No control publications.

Measured recorder CPU 29.29% of **one** core, peak RSS 78.27 MiB, files 1,997,600
bytes. Whole-NVMe writes 14,323,712 bytes include other processes. Free storage
396.41 GB. This is parked workload, not a driving/endurance benchmark.
No autostart/background service installed; finite test ended. Operator must
wait for a new READY before any coordinated manual-drive recording.

Stage 6b rollback (stop only the recorder process first):
`bash /home/jetson/project_atlas/data/backups/2026-10-11-160101-005816539-stage6b-motion-recorder/ROLLBACK.sh`
It removes only the three added scripts, not recordings. No control restart.

Stage 7b installed BMS commit `bff88ac` at 16:03 IST. Files:
`scripts/atlas_daly_transport.py` (`f156c3fe`) and `scripts/daly_bms_node.py`
(`26661b3c`). Nineteen focused tests pass. Only `rover-daly-bms.service` restarted.
Original stage-7 rehearsal refused mixed CRLF/LF baseline; no live edits occurred.
Byte-captured live content matched Git exactly after EOL normalization; adapted
patches passed scratch apply/rollback and final hash checks. This stage was
subsequently **ROLLED BACK** using the command below. Only BMS was restarted.

New verified finding: the recovery supervisor restarted BMS every 60 seconds
while its retry heartbeat was alive, resetting backoff. Its three recovery
events occurred at epoch 1791714801, 1791714861, 1791714921. This explains the
rollout's competing retries, NOT the underlying BLE connection timeout.
Owner confirms phone BMS app disconnected. Neither window had healthy reads.

Offline correction: explicit bounded BMS retry ownership is respected only
while the heartbeat is fresh, including a worker recheck before restart.
Stale/malformed heartbeat retains recovery; battery data remains FAULT/invalid.
BMS JSON health parsing is now whitespace independent. Nineteen recovery tests
(including four new ownership cases), nineteen Daly and sixteen recorder tests
pass. This correction is NOT deployed: supervisor restart needs separate
approval because it also supervises motor-related services.

After-stage 120-second observations: gateway 24/24, median 1.745 ms, max 2.58 ms;
dashboard localhost 24/24, median 43.66 ms but p95 1,941 ms and max 2,483 ms.
No Wi-Fi disconnect, DHCP failure or route switch in either short window.
BMS failures 15 before / 4 after are confounded by process restarts, not proof
of repaired BLE. The original BMS CPU statistic is invalid due to PID changes;
the measurement helper now withholds CPU impact if process coverage changes.
No valid BMS full-window resource comparison is claimed.

Stage 7b rollback, with rover stopped/latched:
`bash /home/jetson/project_atlas/data/backups/2026-10-11-160307-166057524-stage7b-daly-backoff/ROLLBACK.sh`
then `systemctl --user restart rover-daly-bms.service`. No global Bluetooth restart.

Private evidence root: `/home/jetson/atlas_recorder_smoke_KWJkzy` (synthetic
`final_flush`, `final_paced`; failed `live_parked`; accepted `live_parked_corrected`;
network snapshots). Raw evidence is not committed to GitHub.

## Exact network experiment proposed — NOT applied

Current non-secret profile, routes, policy rules, power state and regulatory
domain saved privately as `network_config_before.json` in the evidence root.
Active profile UUID `5b435854-0b46-4747-a608-1647db29add1`. Tailscale to the PC
was direct over LAN (3 ms disco ping), not relayed. Cellular-bound HTTPS returned
204 with Wi-Fi still active: fallback Internet is available, but a forced
Tailscale failover was not tested.

First A/B change should be **runtime Wi-Fi power save only**, while parked:

1. Owner explicitly approves; local keyboard/display recovery available. Keep
   cellular route metric 600 and Wi-Fi metric 50 unchanged.
2. Before changing anything, schedule root-owned timed rollback:
   `sudo systemd-run --unit=atlas-wifi-ps-rollback --on-active=120s /usr/sbin/iw dev wlP1p1s0 set power_save on`
   Confirm the timer is active; if scheduling fails, do not apply.
3. `sudo /usr/sbin/iw dev wlP1p1s0 set power_save off`
4. Run the same gateway/HTTP checks for 120 seconds; let rollback restore ON.
   Confirm restoration locally/remotely. No profile reconnect or reboot.
5. Only if measured benefit is repeatable, request permission to persist
   `802-11-wireless.powersave=2` on the active profile in a separate stage.

Do not combine this with BSSID pinning, DHCP edits, regulatory changes or route
changes. Main-router preference is promising from historical DHCP results but
can block roaming outside its coverage. Domain IN support for the self-managed
driver is unverified; do not assume `iw reg set` will fix transmit power.

## Final status and next actions

| Component | Built | Tested | Deployed | Live verified | Remaining blocker |
|---|---|---|---|---|---|
| Bounded recorder | Yes | 16 offline + Humble readback | Opt-in scripts only | Parked capture; stopped now | Supervised moving/endurance validation; one DDS loss |
| BMS persistent connection/backoff | Yes | 19 Daly tests | Rolled back | No healthy BLE reads | Connection timeout plus supervisor ownership |
| BMS supervisor ownership | Yes | 19 recovery tests | No | No | Approval for scoped supervisor restart and staged rollback |
| Wi-Fi stability | Existing | Two 120 s observations | Unchanged | No loss in these windows | Approved power-save A/B with independent recovery |
| Localization/autonomy | Existing preserved | No new motion tests | Unchanged, autonomy disabled | Not newly qualified | Existing localization/odometry gates |

No physical test is needed now. First approve the separate BMS/recovery stage
if desired; snapshot all three affected files, rehearse exact rollback, restart
only BMS and recovery reporter/supervisor while stopped, then verify no motor
owner restart and sustained retry ownership. On failure restore the three
pre-stage files and restart only those two services. Do not reuse the old
two-file stage-7 package for this three-file correction. Wi-Fi A/B is a separate
approval. A driving capture requires fresh safety checks and explicit consent.
