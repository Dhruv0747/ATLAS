# Stage 28: review of df1c41e and native validation

2026-10-27. Scope: offline source review, simulated serial, PC WSL native fake units. No Jetson connection or deployment; no production restart; no serial/MCU access. Owner rebooted ATLAS during this work, so all later admission evidence must be collected fresh.

## Verdict

GO to request approval for a **maintenance-only deployment**, conditional on fresh live hashes, actual unit/drop-in inventory, safety, resources and rollback checks. NO-GO for physical B1 now. Deployment health verification must precede a separate approval for one read-only B1. No B2 authorization.

## Review findings and implemented fixes

| Finding in df1c41e | Correction and evidence |
|---|---|
| A new watcher could refresh an expired heartbeat before read validation noticed the gap | Heartbeat validates the previous lease first; expiry durably latches ABORTED. Tested process SIGKILL and elapsed heartbeat window. Explicit reconciliation authorizes restoration only. |
| READING session could be reused by multiple CLI invocations | Durable single-use reader claim plus exclusive reader lock. Reader completion/error leaves ABORTED. Tests reject a second claim. |
| Restoration could race a running read if a caller supplied an optimistic port-free callback | Resume/reconcile also require acquiring the reader lock. Native fake test denies restoration while held. Actual CLI separately verifies USB identity and port ownership. |
| Missing/ambiguous state fields could reach permissive branches | Strict held-state schema; IDLE cannot contain a live session. Nonfinite deadlines and ambiguous IDLE rejected. |
| Readback checked the lease around chunks but not each protocol write/read wait | Protocol guard before writes and during bounded read waits; short serial writes fail without retry. |
| Later READ_MEMORY denial escaped normal failure reporting | Denial now records failure evidence and stops; it is not falsely diagnosed as proven RDP. RDP is reported inactive only after A5/5A validation. |
| Restoration existed only as library callbacks | Added explicit reconcile/resume/release CLI gates; no action starts a service automatically. Release requires five seconds of fresh increasing serial packet counts, stable base PID/restart count, E-STOP and zero commands. |
| Original USB helper retried fuser after timeout | B1-specific ownership check queries once and aborts on ambiguity. Does not alter the shared USB helper. |
| Physical exact-part confirmation was only prose | Readback CLI now requires explicit STM32F103RCT6 marking confirmation; family PID alone still cannot prove manufacturer/package. |
| Metadata/startup output could mislead operator | Separate prompt confirmations; guard rechecked between prompts; start event emitted/flushed only after first full flash chunk. Failure says release BOOT0 if held and wait for verified port-release/recovery guidance. |

Lock order: dispatch -> reader (restoration only) -> state. Recovery holds dispatch through bounded systemctl completion; ExecCondition uses state only, avoiding recursive dispatch deadlock. Admission refuses busy dispatch/pending jobs. Any start admitted before maintenance must still finish or be canceled by the controlled stop; begin-read requires inactive base, MainPID/ControlPID zero, no jobs and free verified serial port. Physical entry is never inferred from LEDs.

The state/condition deliberately keeps base telemetry blocked if the MCU may be in bootloader. It never disables unrelated units, E-STOP, command mux or fault reporting. Corrupt state cannot safely auto-release; the independent rollback below provides operator-controlled recovery. Privileged manual bypass or unreviewed third-party serial readers are outside this cooperative interlock's trust boundary.

## Test evidence

- **94 focused offline tests passed** in Ubuntu 22.04 WSL: interlock, recovery regression, byte-level AN3155 simulation, retired-runner gate and actual PTY prompt interaction.
- Native **systemd 249 (249.11-0ubuntu3.23)** user-manager validation passed on the Windows PC's WSL environment. This is real systemd execution of unique fake services, not a mocked systemctl test and not a Jetson production test.
- In-flight native start job rejected maintenance admission.
- Unexpected fake-base exit under maintenance triggered the configured restart path, but ExecCondition blocked ExecStart: execution count remained 1, MainPID 0, inactive. Two subsequent start requests also left count 1.
- Unrelated fake service retained the same PID throughout.
- Reader collision, explicit abort and killed watcher/2-second lease expiry retained the hold.
- One restoration start increased count to 2; its failure did not launch again. Explicit reconciliation/restoration increased count to 3; verified release restored normal Restart=on-failure behavior (count 4).
- Corrupt state prevented launch. Independent fake-only rollback removing the test condition restored the fake service.
- Fake units were stopped and removed afterward. No production names were passed to mutating systemctl commands. No hardware or ROS participants were used.
- Retained local native evidence: WSL `/tmp/atlas-b1-native-result-20261027-reviewed/result.json`. Raw generated test output is not committed; this report summarizes results and the reproducible harness is committed.

Run focused tests using pytest on test_b1_interlock.py, test_stm32_readback.py, test_atlas_sensor_recovery.py, test_b1_recovery_isolation.py and test_b1_operator_prompts.py. Native harness: `python3 project_atlas/tests/native_b1_systemd_validation.py --allow-pc-fake-units --output NEW_DIRECTORY`. Harness refuses non-WSL execution; do not use it on Jetson.

Readback tests cover unknown/invalid identity, invalid/missing capacity, protected/ambiguous option bytes, missing UID, first-error timeout, short write, interruption, unequal passes and hash verification of successful artifacts. Simulated pass mismatch produces no verified full image. START notice is absent on a failed first flash chunk and appears exactly once after genuine simulated chunk delivery. No command outside GET, GET_VERSION, GET_ID and READ_MEMORY is permitted.

## Reviewed installation plan — approval required, not executed

The six candidate runtime files and exact SHA256 values are in `tools/diagnostics/stm32_readback/B1_CANDIDATE_SHA256SUMS.json`. Hash LF package bytes from this commit; do not copy a Windows CRLF-converted checkout blindly. Archive those exact files and verify package/candidate hashes on both hosts.

1. Fresh post-reboot E-STOP/manual-only/zero-command, resource and telemetry checks; transmitter OFF and physical outputs isolated. Compare current live files, all base drop-ins, unit identity and restart owners with reviewed baseline. Abort on unexplained differences or conflicting conditions.
2. Create timestamped rollback directory on Jetson, copy current files and full base unit/drop-in set, record SHA256, permissions, PIDs/restart counts; copy rollback inventory to Windows. Preserve calibrations/maps and all diagnostic evidence.
3. Install interlock module and initialize its private persistent state ONCE as jetson. Never overwrite pre-existing state. Verify IDLE and direct gate success before adding the condition. Install reviewed recovery module, readback, retired legacy runner and supervised frontend. Install ONLY the base-specific ExecCondition drop-in.
4. Approve user systemd daemon-reload and **one atlas-sensor-recovery restart** so its running process acquires the new lock. Do not stop/restart base, motor, E-STOP, Nav2, camera or any other production service during this deployment. Inspect service identities and effective condition; perform only non-mutating gate/status checks on production.
5. Verify new recovery PID/source hash, normal ongoing telemetry, unchanged protected PIDs/restart counts, E-STOP and zero commands. Native fake-unit semantics are already tested; do not simulate a crash in production.
6. Leave state IDLE, no active B1/watch/reader, all production systems healthy. Then report deployment and ask separately for one supervised B1 attempt.

## Supervised operation after separate B1 approval

Keep main switch ON, stable battery supply and the previously verified power/SBUS arrangement. Confirm exact chip marking and physically disconnected actuators again. Snapshot calibration before the approved stop. Verify USB topology rather than trusting tty numbers.

Use interlock `arm` to obtain a session, start an independent supervised `watch --session TOKEN` with durable output, confirm fresh monitor_seen. Then perform the ONE approved base stop. `begin-read --session TOKEN --port VERIFIED_PORT` verifies no process/job owns the base before physical prompts. The supervised frontend performs this gate and asks each button action separately. It must not be rerun after a failure.

Read success requires two complete 262144-byte identical images and matching SHA256 files. Copies on Windows and Jetson must be verified independently. BACKUP STARTED is not a success claim; locally verified readback is not yet verified cross-host backup/restoration.

After reader exit, check port release before asking for normal RESET. Use explicit `reconcile --session TOKEN --port VERIFIED_PORT --confirm-normal-reset` only after an expired/crashed session and actual normal-reset confirmation; then restart the independent watch. Use `resume` with the same arguments to permit exactly one separately approved base start. `resume` does not run systemctl. After the start, `release --session TOKEN --confirm-restored` requires five-second fresh packet progression and unchanged PID/restart count. No wheel movement is needed. Stale stop policy blocks these operations; do not bypass it.

## Independent rollback (does not depend on new Python working)

During maintenance deployment only, no board mode was changed: verify original normal telemetry and E-STOP, restore hash-verified original files/drop-in set using ordinary copy/rename, user daemon-reload, then the approved recovery-service restart. Preserve failed candidate and durable state evidence. Do not remove unrelated drop-ins or change calibration.

If the board could be in bootloader, **do not remove the condition or reset the latch**. Keep the independent safety/fault monitor and owner present. Confirm no reader/open descriptor or pending job; obtain normal-reset confirmation with actuators disconnected. If the new module itself is broken or state corrupt, separately approve the ordinary-file rollback ONLY after that physical reconciliation, verified port release and continued E-STOP/zero commands. Restore prior recovery code and base unit/drop-ins; approve a controlled base start and require fresh telemetry. Failure remains latched/NO-GO, not an automatic retry. Do not leave uncertain board attachment unattended.

## Remaining limits

Native tests prove the reviewed user-manager behavior on PC systemd 249, not the post-reboot Jetson's exact current unit configuration. Live hash/unit/version/admission verification is therefore mandatory at deployment. No physical chip identity, RDP, flash size, backup, UART throughput or restoration timing has been measured in this task. The first actual B1 remains a single supervised attempt with immediate abort, never a guarantee of backup success. Existing resource/safety limits, voice/UI and unrelated systems are unchanged.

Reference for condition exit semantics: https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html#ExecCondition=
