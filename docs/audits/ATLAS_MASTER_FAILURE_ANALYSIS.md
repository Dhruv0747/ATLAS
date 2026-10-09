# ATLAS master failure analysis

Updated: 2026-10-09, Asia/Calcutta. Initial evidence-backed baseline, **not a completed exhaustive historical investigation**.

Source baseline: `3d66c3812c968796fed70b7f32dae511aadeed45`, branch `agent/fix-mapping-footprint`.
Publication revision is the Git commit containing this file; use `git log -1 --format=%H -- docs/audits`.
No physical movement, firmware flashing, safety bypass, calibration or navigation changes are authorized by this report.

## Findings in plain language

Latest bounded follow-up: [stationary particle-support audit](ATLAS_AMCL_PARTICLE_COLLAPSE_2026-10-09.md)
confirmed that 2,000 published AMCL particles can occupy one effective pose
with near-zero covariance at a previously wrong map location. The saved drive
also exhibits collapse. Forced 1 Hz updates/resampling require an isolated
policy experiment; high particle count and low variance are not independent
confidence evidence. No production change or localization repair is claimed.

ATLAS has recurring failures because several dependent layers have changed and have not been jointly qualified on a frozen hardware/configuration baseline. There is **no single proven cause covering every failure**.

1. Physical encoder response, metric calibration and serial message freshness have repeatedly been confused. Historical replacements genuinely restored missing counts, but a fresh board packet does not prove each wheel measures distance correctly.
2. USB role ambiguity and shared discovery locking can keep a healthy motor owner from starting. A service restart can therefore worsen availability rather than cure it.
3. Some watchdog/recovery logic has itself caused interruptions: the September truncated-JSON parser is a demonstrated example.
4. Today's motor commissioning has separate readiness/timing and BMS connection blockers. Six preserved Oct8 sessions issued zero pulses; these are not six M3 hardware failures.
5. Mapping has both test-process faults (driving before active recording/SLAM readiness) and remaining odometry/geometry questions. Repeated manual loops without targeted instrumentation do not resolve those questions.
6. Hardware replacements, sensor migrations and configuration changes invalidate earlier qualifications. An August success with different motor mapping cannot certify October operation.
7. Resource pressure may expose deadlines, but CPU load alone does not identify a culprit. Current evidence does not justify replacing the Jetson or adding another computer.
8. The Visual Cloud agent is active but its configured destination is the checked-in example hostname. The local history database is about 26.5 GB and its last modification predates this check by several days. An active service is therefore not proof that cloud history is arriving; do not add a second monitoring stack before repairing or retiring this path.
9. The Oct9 [cross-bag localization audit](ATLAS_LOCALIZATION_CROSS_BAG_2026-10-09.md) found recurring wheel-model/IM10A heading conflict during recorded turns. An isolated saved-map AMCL replay improved some candidate EKF metrics but worsened final-window position span and did not reproduce five live jumps. The candidate is not deployed; physical steering/traction/geometry contribution remains unresolved.
   A read-only steering hardware review confirmed the active path is Yahboom
   PWM front/rear channels 2/1, not the legacy ST3215 bus servo. The current
   controller supplies commanded angles only. Wheel odometry applies those
   commands as if they were measured road-wheel angles; physical linkage
   geometry and slip have not been separated. No production calibration changed.

## Evidence vocabulary

- **CONFIRMED:** the stated observation/mechanism has direct logs, inspected source or reproducible historical evidence. It does not mean every suspected cause is confirmed.
- **SUSPECTED:** plausible explanation with named alternatives; needs discrimination.
- **UNRESOLVED:** fix absent, rejected, incomplete, or validation inadequate.
- **VERIFIED FIXED:** only a specifically scoped defect with reproducible verification. Never an eternal no-failure guarantee.

The registry separates confidence from resolution. A confirmed failure can remain unresolved. Historical written test reports are retained as historical reports; this audit does not pretend to have rerun them.

## Coverage and missing evidence

| Source | Reviewed/inventoried | Limit |
| --- | --- | --- |
| Git | Full non-shallow clone; fetched current remote refs; 268 reachable commits indexed from 2026-08-04 to Oct8 across all available refs | Selected relevant diffs deeply reviewed; **not every diff** |
| GitHub branches | Five remote branches: main, active fix branch, offline-agent plan, mapping-session gate, secure-runner setup | Deleted/unreachable history may be absent |
| PRs/issues | API returned PRs 1,2,3,4,6,7,8; #7 open, others closed. No separate issue entries returned | No assumption about unavailable/deleted records |
| Comments/reviews | Issue comments, PR review comments and reviews of all seven PRs returned empty; default-branch commit-comment count search returned none | Not proof no private/deleted review ever existed |
| Actions | Workflow ATLAS Read-Only Health exists on `origin/main`, not the active fix branch; API returned total_count=0 runs. Jetson has the corresponding root-owned read-only health wrapper | No run artifacts available; do not conflate cross-branch presence or installed wrapper with a successful recent health run |
| Local developer sessions | 186 JSONL files found; 131 contain ATLAS/project identifiers | Only inventory/search and supplied conversation history reviewed; **full transcripts not yet audited**; credentials/private text must not be published |
| Jetson journals | 11 retained boots spanning Oct1–Oct9; targeted base/BMS/recovery/LiDAR observations | Older journals missing from retention; do not infer no earlier failures |
| ROS logs | Log directory exists; six Oct8 lifted evidence files parsed read-only | Full ROS log corpus not enumerated/reviewed and all bags not replayed in this pass |
| Mapping evidence | Reviewed Aug24, Oct4 and detailed Oct8 reports; confirmed replay artifact directories still exist | Existing report metrics distinguished from independent reruns/ground truth |
| Future sessions | Repository procedure added to AGENTS.md | No autonomous background watcher or unlimited future execution promised |

Raw chats, email address, credentials, device serial numbers and full logs are intentionally excluded from publication. The complete timeline filename is the requested canonical destination, not a claim that every historical event has been recovered.

## Cross-system chains

| Chain | Evidence level | Engineering implication |
| --- | --- | --- |
| Identical USB roles → passive discovery lock → GNSS retries → motor startup blocked | Confirmed historical contention/workaround | Repair bounded fairness, not unsafe concurrent serial access |
| Oversized health JSON truncated → parse failure → healthy base restart → telemetry interruption | Confirmed exact September defect, scoped live verification | Preserve full bounded structured parsing and stationary restart gates |
| Fresh serial receive thread → delayed ROS cache refresh → stale encoder safety snapshot | Confirmed age discrepancy | Instrument stages; do not label every event a physical USB disconnect |
| BLE connect timeout → unhealthy battery report → commissioning rejected | Confirmed current chain | Charged battery does not make telemetry trustworthy |
| BLE fault → bounded service restart → healthy sample → BLE failure returns | Confirmed Oct9 sequence | A RECOVERED line is not endurance evidence |
| Example Visual Cloud URL → repeated DNS failure → local history not updated | Confirmed Oct9 configuration/runtime observation | Diagnose the existing pipeline and retention before adding Grafana, Prometheus or n8n |
| Wheel model/timing error → inaccurate pose prior → beneficial SLAM correction | Suspected source; better post-correction scan fit confirmed | Do not suppress correction just to make a plot look smooth |
| CPU contention → callback delay → false offline indication | Plausible, not uniquely established | Measure under real workload; preserve essential sensors |
| Servo re-energization/reconnect → shared I2C outage | Historical code regression documented; universal electrical causation unproven | Distinguish software restart loop from measured rail collapse |

## Which earlier changes helped?

- Early encoder replacement restored a specific dead channel, with forward/reverse deltas. This is hardware evidence for that historical channel, not diagnosis of current M3.
- September recovery parser fix had focused regression coverage and two stationary live observations with unchanged base PID and no spurious restart. Registry ATLAS-008 is VERIFIED FIXED **for that exact defect**.
- September10 one-restart and degraded-speed safeguards have recorded controlled tests. They prove bounded behavior in those scenarios, not navigation accuracy.
- Planner/controller alignment removed a documented configuration contradiction. Preserve it; no current mission pass is inferred.
- BMS MTU/frame and response-driven changes addressed identifiable parsing/deadline problems. Current BLE connection failures remain distinct and unresolved.
- Idle observability optimization reduced measured process CPU without changing freshness thresholds in its recorded window. It is not whole-system load certification.

## What did not solve the problem?

Preserve these negative results; do not repeat without new evidence:

- Aug24 120-beam AMCL trial and beam skipping were rejected in `e6b2a47` and `ca8b601`.
- Oct8 disabling loop closure reproduced identical largest correction; not deployed.
- Velocity-only wheel fusion improved one translation metric but worsened endpoint heading and did not pass; not deployed.
- Zero TF offset worsened translation correction despite smaller yaw correction; rejected.
- Guessed per-ray timing/rotation compensation did not consistently improve residuals; no deskew deployment justified.
- Half/zero commanded-angle normalization did not establish a better current wheel model; preserve steering.
- Commissioning write/status coalescing failed heartbeat validation and was reverted.
- Five-second entry readiness is useful fail-closed behavior but a later heartbeat still expired.
- Pausing GNSS to let the motor board start and restarting BMS provide temporary recovery, not verified permanent repairs.

See [Oct8 detailed analysis](../SLAM_TURN_CORRECTION_ANALYSIS_2026-10-08.md) and [lifted audit](../LIFTED_TEST_FAILURE_AUDIT_2026-10-08.md).

## Important corrections to earlier interpretations

- A ~0.747 m change in a map→odom transform component is **not** automatically a 0.747 m physical robot displacement. Compose both hypotheses with the same timestamp/odom pose. The reviewed event yielded ~0.232–0.236 m robot-position correction.
- Overlapping critical encoder windows are not independent failure trials. At the original 133.928 s event, cited faults occurred **after** the event, not before.
- Recorded message count is not proof every scan was processed.
- Internal odometry returning near zero is not surveyed physical return-home accuracy.
- No current board-replacement recommendation is supported solely by freshness failures.
- Boot wall clocks changed before time synchronization: preserve boot ID/monotonic time, not wall-time sorting alone.
- Existing docs say IM10A authority was revoked in September and later used in October. Qualification must be verified against actual deployment; old labels are insufficient.

## Safe shortest path

Follow [current blockers](ATLAS_CURRENT_BLOCKERS.md). First establish reliable, stationary telemetry and test-channel timing. Then one discriminating M3 test, not another uninformed route repetition. Reuse saved bags to resolve model and map acceptance questions before asking for new movement.

No percentages or fixed completion dates are justified by the available evidence.

## Oct9 stopped-runtime observability snapshot

Read-only checks found motor/base running with PID 3120, zero reported service restarts and zero outputs; this is an idle snapshot, not a heartbeat or encoder endurance pass. The BMS alternated healthy readings near 13.20 V / 90% with connection-stage deadlines. On failure the node marked the reading invalid, which is the correct fail-closed freshness behavior; the connection cause remains undetermined. The Bluetooth device was disconnected, unpaired and untrusted when sampled, and the transport starts a new `gatttool` session per poll. Connection churn is a testable hypothesis, not a proven root cause.

The Jetson showed about 60.7 °C, 2.38 GB available RAM and no failed user units in the sampled window. This does not certify full-load control timing. The dashboard responded HTTP 200 locally. The Visual Cloud agent repeatedly logged DNS errors for `atlas-visual-cloud.example`; the checked-in `cloud_url` is a placeholder. The local history SQLite file was 26,501,885,952 bytes and last modified on Oct4. Its 86,400-row retention limit does not reclaim allocated SQLite pages on deletion, so disk size alone is not evidence of ongoing ingest. The NVMe still had about 373 GB available. No database compaction, service restart or deployment was performed.

A later source audit qualified the BMS freshness statement above: JSON status was marked invalid on read failure, **but scalar voltage/current/SOC topics were republished from the previous successful snapshot**. Those scalars have no validity flag. The agent supervisor subscribed to scalar SOC, so a failed connection could refresh its battery age incorrectly. This is a confirmed data-contract defect independent of the unproven BLE radio cause. See [BMS freshness repair](BMS_FRESHNESS_REPAIR_2026-10-09.md).

At 10:07 IST a fresh dashboard API sample reported encoder state `READY`, packet freshness true, selected wheels `[1,2,3,4]`, and no excluded wheels. This is evidence of the current selection configuration only, **not** M3 physical distance accuracy. In the same sample, autonomy phase was `FAULT` with `STOP: SLAM MAP DATA LOST`. The earlier three-encoder narrative must not be carried forward as a current runtime fact, and encoder readiness must not be equated to whole-rover autonomy readiness.

The later recorded **manual** Hall-to-Dhruv return provides a stronger moving
counterexample to stationary `READY`: 32 roughly 10 Hz samples had applied
traction with encoder consensus `CRITICAL` and autonomy revoked; M3 was the
most frequently rejected wheel. Five >0.5 m AMCL pose steps followed the last
remote command, not a 20-second sensor-message gap. Wheel yaw-rate integration
and IM10A gyro integration differed by about 49 degrees over the driven
window. A shorter wheel-odometry **endpoint** displacement is not itself a
wheel-scale fault, since the integrated wheel path was about 6.77 m and the
trajectory curved. See the [Oct9 navigation gate](ATLAS_NAVIGATION_GATE_2026-10-09.md)
for timing and limitations. Keep autonomous navigation unqualified; do not
blindly change wheel scale, EKF fusion or AMCL tuning from this bag alone.
An isolated same-bag EKF A/B then changed only wheel X/Y pose fusion. The
velocity-only variant improved median saved-map scan endpoint proximity from
23.1% to 50.2% across 31 samples and kept net heading close to IM10A gyro;
current fusion's heading and final scan proximity were much worse. The
velocity-only result is still incomplete and conflicts with a mixed Oct8
comparison, so it is **not** a production fix. The deployed read-only map
display now exposes AMCL uncertainty and recent jumps instead of presenting
a fresh but uncertain TF as a precise pose. It cannot repair AMCL itself.
An Oct9 replay-fidelity follow-up found the missing AMCL no-motion service
heartbeat in the original journal. One isolated full-bag replay with its
approximately 1 Hz cadence matched the original 384/80 total/post-stop pose
counts and reproduced two large stationary jumps, versus five live. This
explains the earlier replay update-count mismatch but is not an exact failure
reproduction or a validated localization repair; production remains unchanged.
The matched scan-window follow-up found that original post-stop events 1 and 4
favored the *old* pose on all seven selected scans each, while both replay
jumps favored the new pose on every selected scan. Both had broad particles,
but published weights are uniform and do not expose pre-resampling AMCL
likelihood; the remaining hypothesis-selection mechanism is unverified.
A diagnostic-only AMCL 1.1.20 shadow build now exposes pre-resampling weights
and chosen-cluster scores while keeping production AMCL and TF unchanged.
One paced stationary capture verified the instrumentation but did not
reproduce the old five jumps or qualify autonomous navigation; see the
[trace audit](ATLAS_AMCL_SHADOW_TRACE_2026-10-09.md).

Recommendation: retain Jetson-local safety and essential diagnostics, first resolve BLE freshness and motor timing with bounded evidence, then decide whether Visual Cloud should connect to a real authenticated PC endpoint or remain local. Measure overhead and data growth before enabling any additional collector. PC-side n8n/analytics are optional consumers, never dependencies of autonomous control.

Voice improvement is separately queued in the [local ASR evaluation plan](ATLAS_VOICE_ASR_EVALUATION_PLAN.md). The current active recognizer is cloud-based and the wake phrase is checked after cloud transcription; local speech output and optional local text reasoning do not yet make microphone commands offline. Whisper/faster-whisper must earn deployment through measured multilingual recognition and Jetson workload tests, with the existing safety path and recognizer preserved.

## Reproducible read-only evidence commands

Run from the repository (credentials are configured separately; never paste them into reports):

```sh
git log --all --reverse --format='%H %aI %s'
git show 5c9064c -- CHANGELOG.md
git show d77195b -- CHANGELOG.md
git show 5f3e309 -- CHANGELOG.md
gh api repos/Dhruv0747/ATLAS/branches --paginate
gh api 'repos/Dhruv0747/ATLAS/pulls?state=all' --paginate
gh api repos/Dhruv0747/ATLAS/actions/runs --paginate
```

On Jetson:

```sh
journalctl --list-boots --no-pager
journalctl --user -b -u rover-daly-bms.service --no-pager
journalctl --user -b -u atlas-sensor-recovery.service --no-pager
systemctl --user show rover-base-telemetry.service -p MainPID -p NRestarts
/usr/bin/python3 /home/jetson/project_atlas/data/diagnostics/audit_lifted_failures.py
```

For bounded direct topic inspection, source Humble and use the deployed ROS environment, `timeout -k 2 8 ros2 topic echo ... --once --no-daemon`. Do not mistake a single CLI timeout for hardware failure. Avoid unrestricted test discovery: legacy scripts may actuate hardware on import.

## Continuous investigation procedure

1. Read this registry before proposing a fix; match symptom, hardware generation and dependency chain.
2. Append dated events, evidence path/commit and hypotheses; never erase rejected fixes or old results.
3. Find earliest failing component, not merely the last dashboard that went red.
4. Make one scoped change; record baseline, rollback and acceptance before deployment.
5. Reuse existing evidence where it answers the question. Request movement only for an unmet physical gate.
6. Link all validation to source/config/hardware identity; preserve stale/invalid data as invalid.
7. Publish coherent milestones, not commits or restarts solely for activity.
8. Mark VERIFIED FIXED only for a specified defect and test scope, with remaining limits.
9. Future available sessions expand the evidence inventory; inaccessible history remains explicitly missing.

## Deployment boundary for this audit

This audit itself is documentation-only. Earlier in this same conversation, before the expanded audit request, a stage-label-only BMS diagnostic was tested (12 passing tests), deployed and its service restarted; failures still recur. Those changes are preserved separately in commit `221af9c`. No motor owner restart or actuator command was issued in this audit. No claim of a full repair is made.

