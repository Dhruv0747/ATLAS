# One monitoring recovery transaction — offline preparation

## Correction for attempt 2: startup deadline and launcher stop only (2026-10-31, offline; NOT executed)

**Measured exporter start** (systemd `Starting` → `Started`, Jetson journal, including the guarded ExecCondition):

| Start | Duration |
|---|---|
| 2026-10-30 20:26 | 3.629 s |
| 2026-10-30 20:45 | 3.623 s |
| 2026-10-31 11:40 (attempt 1) | **3.598 s** |

- Attempt 1 waited only 3 s from watchdog-ready (11:40:02.575) and gave up at about 11:40:05.6. Systemd reported the exporter started at 11:40:06.177.
- Watchdog start: 2.217 s. Firewall start: 0.249 s (deadline 8 s, unchanged).

**Fix in `recover_once.py` (the only changed package file):**
- `EXPORTER_START_S = 12.0` (3.3x the slowest measured start, finite). `WATCHDOG_START_S = 20` and the outer `START_STEP_S = 25` supervised bound are **unchanged** and remain the hard cap.
- Launcher stop is idempotent. After `systemd-run --wait --collect`, a finished unit is already removed: attempt 1's extra stop exited 5 and masked the real error. `stop_if_running()` stops only a loaded, running unit, never raises, and the original exception always propagates.
- New attempt identity: `/var/lib/atlas-monitoring-recovery-20261031-2` and `atlas-monitoring-recovery-once-20261031-2`. Attempt 1's directory and unit name are retained evidence and are never reused. Stage to `/opt/atlas-monitoring-recovery-20261031-2`; the attempt-1 `/opt` directory stays as it is.

**Unchanged (byte-identical):**
- `guard.py` (27d4cacae470): first-fault preservation; 75 % CPU, 80 % RAM, < 70 C.
- `activate_timestamp_retry_once.py` (the sampler).
- The nft table and all three units.
- Archive-before-reset, firewall protection, fail-closed cleanup, client confirmation, the 300 s window and the 410 s / ~440 s independent expiry.

**Focused tests:** `test_monitoring_recovery_transaction.py` **37/37 pass**: the 29 existing tests plus 8 new ones. The new tests reproduce the 3 s failure with the measured 3.629 s start, pass it with the new deadline, check that a never-started exporter still fails within the bound, check the bound constants and the new identity, and check the idempotent, non-masking stop.
- `test_monitoring_recovery_native.py` (4) is opt-in PC/WSL only (`ATLAS_FAKE_SYSTEMD=1`). It was not run in this session.
- Guard tests were not repeated: guard.py is unchanged.

**Package (PC only):** `monitoring-recovery-transaction-20261031-2.tar.gz`. Members root:root 0644; reproducible gzip.
- Archive SHA256 `b997bcd4e503e9bd9900012d52dc3a17091fdc619094afbd7f73354f1da7c167`
- Manifest SHA256 `0891413d345b271b6796cd67b61dbd93ffc0a485188523582f664605704607b4`
- Use the staging/run/confirm/abort sequence below with `-20261031-2` in every path and unit name, and the new archive hash. Do **not** reuse attempt 1's paths.

**On-device read-only check (11:5x):**
- Attempt-1 evidence present; `-2` paths absent.
- Monitoring units inactive (exporter enabled/on-failure as restored); no 9118 listener; no recovery timer.
- Live guard hash 27d4cacae470 matches.
- Root-private state hashes are verified by the transaction itself before any change. It refuses on mismatch.

The original October 30 watchdog rejection remains UNKNOWN. The fault latch was not cleared, nothing was started, and the firewall was not changed.


## Controlled execution result — 2026-10-31 11:39:53–11:40:09 IST

**FAIL; cleanup VERIFIED. NO-GO for another attempt without correction/review.**
This supersedes the preparation GO below. Exactly one owner-approved attempt
used da86a6e and archive SHA256 157b00723d3e4de2847a191f87629cd8fdd8fc9f608963b6a322b2f3b4efc4ff.
All seven package hashes and exact installed unit/firewall configuration matched.

Timeline from the existing systemd journal:

- 11:39:53 transaction worker started; independent expiry armed.
- 11:39:59 firewall unit started successfully.
- 11:40:02 watchdog ready; exporter startup began.
- 11:40:06 wrapper rejected `startup deadline: atlas-monitoring-exporter.service`.
  Systemd recorded exporter started at the same second. The wrapper's 3-second
  exporter sub-deadline was insufficient for this roughly 4-second startup,
  which includes its existing guarded ExecCondition. This is a transaction
  startup-deadline failure, not evidence of a CPU safety rejection.
- 11:40:07 automatic cleanup stopped exporter/watchdog/firewall.
- 11:40:09 transaction finished with failure; 16.072 s runtime, 1.330 s cgroup
  CPU time. Launcher then tried to stop its already-collected transient unit,
  producing an additional exit-status-5 exception. This did not cause the
  original timeout and did not prevent cleanup.

Owner's root-only evidence summary: result FAIL / cleanup VERIFIED, original
cause UNKNOWN; all six original-state checksums PASS (including the evidence
lock). Restored FAULT.json SHA256:
3715b150b880ed06d9e21f25006b81a699693328bb77a80155cf148dcdb1ae97.
Root nft table inventory contains metainfo only; no monitoring table remains.
Evidence directory: `/var/lib/atlas-monitoring-recovery-20261031/`, including
`original-state/`, `state-manifest.json`, `failure.json`, `result.json`, and
`samples.jsonl`. Raw private logs were not committed.

Twelve accepted transaction samples (not a 300-second steady-state test):

| Metric | Average | Peak |
|---|---:|---:|
| Whole-Jetson CPU | 65.341% | 73.377% |
| RAM | 59.871% | 60.063% |
| Maximum trustworthy temperature | 62.059°C | 62.218°C |

Final captured sample: E-STOP latched, manual-only/uncommissioned, zero commands
and motor speed, unchanged encoders [114,-137,-155,-178], fresh required topics.
Independent postflight: all monitoring MainPIDs=0, inactive; no 9118 listener;
no temporary drop-ins; exporter original Restart=on-failure/enabled restored;
watchdog/firewall Restart=no/static restored; independent expiry inactive.
Recovery PID1982/NRestarts0, Dashboard2064/0 and MCU3487/1 unchanged. Cleanup's
protected-service and unrelated-rule comparisons passed.

Prometheus target DOWN/connection refused after cleanup; actual Grafana page
shows DOWN/UNAVAILABLE. Live-data validation did not pass, no client confirmation
was issued, and no 300-second observation completed. Exporter steady-state
overhead cannot be measured from this short startup; the 1.330 s figure belongs
to the transaction cgroup, not the exporter alone.

Next scoped work, not performed: correct the exporter startup deadline within
the existing supervised bound, and make post-collection launcher stop handling
idempotent; focused offline validation before any separately approved attempt.
No retry, threshold change, unrelated service restart or PR merge. The original
October 30 watchdog rejection remains UNKNOWN and unresolved.

## Historical preparation status (before the single execution)

Status: **offline PASS; GO for one separately approved execution, subject to
fresh on-device admission. NOT deployed or executed.** Original October 30
watchdog rejection remains UNKNOWN; this does not fix or explain that trigger.

`recover_once.py` reuses the unchanged first-fault guard and the existing
activation sampler. It never calls the old activation installer. Only the three
optional monitoring units may be started/stopped; no ROS node is created.

## Transaction guarantees and limits

- Fixed, exclusive attempt directory `/var/lib/atlas-monitoring-recovery-20261031`.
  Its existence rejects another `start`. Never delete it to rerun.
- Fixed installed guard/exporter and retained-state hashes; exact original unit
  and firewall configuration checks; unexpected overrides/evidence reject.
- Archive and SHA256-verify every retained state file before reset, with fsync
  and atomic writes. Limit state to 64 files/1 MiB; journal to 150 entries/1 MiB;
  sample log to 256 KiB. Evidence stays root-private on Jetson, never in GitHub.
- Three measured one-second admission samples after read-only preparation.
  Admission CPU <75%, RAM <80%; continuous existing guard CPU <=75%, RAM <=80%,
  temperature strictly <70 C. Existing freshness, latched E-STOP, manual-only,
  uncommissioned, zero commands/speed and unchanged encoder checks are reused.
  Missing, malformed and timed-out data reject, never become zero/PASS.
- Systemd-supervised worker with `Restart=no`; all three optional units receive
  dedicated runtime `Restart=no` overrides. Exporter boot enablement is
  temporarily removed before rearm. No application or existing unit file is
  replaced. The system daemon-reload affects only loading these optional drop-ins;
  it does not restart services or reload the ROS user manager.
- Reset only the verified old FAULT.json and stale observer-active.json after
  archival under the existing operations/evidence locks. One firewall start,
  then one exporter start (dependencies pull watchdog). No retries.
- Firewall verified before exporter start; permitted TCP 9118 source remains
  192.168.1.6 via wlP1p1s0 to 192.168.1.16; other TCP 9118 traffic is dropped.
  Tailscale/iptables baseline and protected user-service identities are compared.
- Main-thread one-second safety sampling continues while bounded systemd commands
  run. Startup deadlines: firewall 10 s, exporter/watchdog 25 s. A sample's
  existing two-second deadline remains; this is not a hard real-time guarantee.
- Observe for 300 seconds from first start. Worker runtime cap 330 s.
  ExecStopPost cleanup also runs for abnormal exit/SIGKILL. Systemd can spend
  30 s stopping the worker AND 30 s on ExecStopPost. Independent expiry is
  therefore **410 s**, after those allowances, with a 30 s cleanup timeout:
  approximately **440 s**, plus timer/scheduler latency. This deliberately
  supersedes the earlier 360 s proposal. No threshold or retry allowance changes.
- Durable local success also requires explicit client confirmation during this
  attempt. Original monitoring restart policy/enabled state is restored without
  restart. A final independent guard check precedes PASS. Cancellation failure
  after durable PASS cannot accidentally trigger rollback; expiry rechecks health
  and original policy before accepting that commit.
- Failure requests shutdown BEFORE attempting evidence restoration. Cleanup
  retains any NEW fault; otherwise restores exact archived old latch under the
  evidence lock. Restore original enablement only after stopped/listener-free,
  verified firewall cleanup and a retained latch. If cleanup cannot prove this,
  leave monitoring stopped/disabled where achieved and retain protection and
  temporary Restart=no, report FAILED; never force deletion or restart.

## Package preparation (PC only; completed for review)

Package members, normalized to LF, are listed in `RECOVERY_SHA256SUMS`:
`recover_once.py`, `guard.py`, `activate_timestamp_retry_once.py`,
`atlas-monitor.nft`, both firewall/watchdog units and exporter unit template.
The packaged guard is the same installed first-fault correction. Cleanup imports
that frozen verified guard so drift in the live guard cannot prevent loading
cleanup. Package SHA256 checks and root-only ownership are mandatory.

No full plugin, service installer or new monitoring framework is included.
Do not copy these files over `/usr/local/libexec`, `/etc/systemd/system` or the
existing exporter. Stage only this separate reviewed package, after approval.

Prepared archive: `monitoring-recovery-transaction-20261031.tar.gz`.

- Archive SHA256: `157b00723d3e4de2847a191f87629cd8fdd8fc9f608963b6a322b2f3b4efc4ff`
- Manifest SHA256: `bda4194bc2085f3c7ccc151b9773f03bc77cdaf8d7c8f1c083a88c0b8c98dc5f`

The package is prepared on the PC only, not copied to Jetson. Original file
owner/group/mode and mtime/ctime are recorded alongside the byte archive.

## Exact execution sequence — NOT authorized by this document

Approval must cover: one archival/reset accepting UNKNOWN original cause; optional
monitoring starts; temporary monitoring-only Restart=no/system daemon-reload;
temporary exporter disable/restore; expiry cleanup and the revised ~440 s bound.
Administrator passwords belong only in the local Jetson terminal.

1. Confirm the approved package tar/manifest hashes against the review report.
   Copy the verified extracted seven files plus manifest to the new root-owned
   directory `/opt/atlas-monitoring-recovery-20261031` (0755 directory, root:root
   files 0644). Do not reuse an existing directory or overwrite installed files.
   Installation of this transaction package does not start a service.
   Once the separately approved copy is at the path below, exact staging is:

   ```sh
   cd /home/jetson/project-atlas-migration &&
   printf '%s\n' '157b00723d3e4de2847a191f87629cd8fdd8fc9f608963b6a322b2f3b4efc4ff  monitoring-recovery-transaction-20261031.tar.gz' | sha256sum -c - &&
   sudo /bin/sh -c 'set -eu; umask 022
   mkdir /opt/atlas-monitoring-recovery-20261031
   tar --no-same-owner -xzf /home/jetson/project-atlas-migration/monitoring-recovery-transaction-20261031.tar.gz -C /opt/atlas-monitoring-recovery-20261031
   cd /opt/atlas-monitoring-recovery-20261031
   sha256sum -c RECOVERY_SHA256SUMS'
   ```

   A pre-existing target directory aborts staging. Do not remove it to force a
   retry. Confirm all files are root:root/0644; `load()` rejects writable files
   or ancestors. The archive is hash-checked before its root extraction.
2. With the owner present and the rover stationary, run **once** locally:

   ```sh
   cd /opt/atlas-monitoring-recovery-20261031 &&
   sha256sum -c RECOVERY_SHA256SUMS &&
   sudo /usr/bin/python3 -I -B recover_once.py start
   ```

   Systemd, not the terminal, owns the runtime cap and cleanup. Do not wrap it in
   an old activation command or repeat it. Ctrl+C requests transaction stop;
   independent expiry remains armed even if the terminal/SSH disappears.
3. During the 300-second window, verify the existing Windows Prometheus target
   is UP with fresh samples, Unix-second timestamps plausible against current
   time, real Grafana values and missing/unavailable fields not presented as
   healthy zeros. Do not increase scrape frequency or induce outages. Only
   after those checks actually pass, use a second local terminal:

   ```sh
   sudo /usr/bin/python3 -I -B /opt/atlas-monitoring-recovery-20261031/recover_once.py confirm-client
   ```

   This is an explicit owner attestation, not an automated Grafana browser test.
   It binds to this attempt's running identities and boot ID and expires after
   310 s. If PC verification is missing or fails, do not attest: transaction
   fails and cleans up. No permanent Windows dependency is introduced after a
   successful validation.
4. Report the root-only `result.json`, `failure.json` if present, sample timeline,
   service identities and cleanup state. The original fault is still UNKNOWN
   even if this single recovery succeeds. Reboot recovery remains unverified.

## Exact abort and manual rollback

For an in-progress attempt, stop only its supervisor; ExecStopPost handles cleanup:

```sh
sudo systemctl stop atlas-monitoring-recovery-once-20261031.service
```

If cleanup reports FAILED, do not repeat `start`, remove evidence, reset-failed,
flush rules or manually start the exporter. Inspect the local result and journal.
After confirming the transaction worker and its cleanup have exited, the reviewed
monitoring-only manual rollback is:

```sh
sudo /usr/bin/python3 -I -B /opt/atlas-monitoring-recovery-20261031/guard.py rollback &&
sudo /usr/bin/python3 -I -B /opt/atlas-monitoring-recovery-20261031/recover_once.py cleanup
```

This stops monitoring, verifies no 9118 listener, removes only the exact owned
table, retains/restores a latch and restores only the attempt's optional unit
policy/enabled state, without starting anything. It also handles an explicitly
approved rollback after a successful recovery. If the first command refuses,
STOP: do not proceed to rule deletion or configuration restoration. Independent
expiry is a single cleanup fallback, not another recovery/start attempt.

The actual existing application/configuration files are never replaced, so their
rollback is hash verification, not copying an older version. Do not roll back the
installed first-fault fix. Original evidence remains byte-for-byte in
`original-state/` with `state-manifest.json`; new evidence is retained separately.

## Focused validation

2026-10-31: **75 tests passed** in Ubuntu 22.04 WSL (13.65 s): 29 transaction tests,
4 native systemd fake-unit tests, 42 existing guard tests. No live Jetson test.
The final archive-metadata addition reran only the 29 affected transaction tests:
29 passed in 0.84 s. All seven package checksums and root-owned package import
were separately verified offline; no runtime action was invoked by that import.

Coverage: complete simulated success/firewall failure/exporter failure/resource
failure/interruption; archive/hash/corrupt/symlink/quota/write failure; second
attempt rejection; fault-writer locking; original policy restoration; failed
cleanup; missing client confirmation; cancellation failure after commit and
post-rename write failure. Native fake-unit tests prove timeout, worker SIGKILL,
cleanup termination and a SIGTERM-resistant worker plus stuck cleanup before
independent expiry; all fake units have no automatic restarts.

Independent read-only review: initial important findings corrected; final review
PASS for offline implementation. Unchanged unrelated ROS safety suites were not
repeated. These results are not a physical safety or reliability acceptance.

Remaining risks: original trigger UNKNOWN; configuration/evidence may drift before
execution; new resource rejection may occur; systemd/filesystem/kernel failure
can prevent guaranteed cleanup. Such inability is FAILED/manual intervention,
never PASS. A killed/offline Jetson cannot be made recoverable by this wrapper.
No automatic reboot rearm, fault clearing or second start is provided.
