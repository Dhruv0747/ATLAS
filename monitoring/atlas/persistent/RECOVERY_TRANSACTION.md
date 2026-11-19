# One monitoring recovery transaction — offline preparation

## Attempt 5 result: PASS (2026-10-31 15:55:14 – 16:00:27 IST)

`result.json` = `{"cleanup": "NOT_NEEDED", "grafana": "OWNER_CONFIRMED", "result": "PASS"}`; the transaction exited with status 0 after a runtime of 5 min 12.8 s.

| Item | Evidence |
|---|---|
| Preflight 15:51 | Encoders stationary over 10 s at [107, -126, -268, -164]; E-STOP latched, manual-only, commissioning off, commands 0; CPU 61.2 %, RAM 63.5 %, 62.4 °C. The earlier change from [104, -126, -183, -164] (manual handling between 14:15 and 15:01) is recorded as history, not current motion. |
| Prometheus | Target UP from 15:55:42; 221 series; 0 stale topics; E-STOP = 1 |
| Confirmation | `confirm-client` ran at 15:57:02 (target 15:57:14, latest 15:59:14), after Prometheus PASS and the owner's Grafana check |
| Final state 16:03:45 | Firewall, watchdog and exporter active, 0 restarts. Exporter `enabled` with restart policy `on-failure`; no override drop-ins; expiry timer inactive; 9118 listening on 192.168.1.16 only. |
| Rover | E-STOP latched, manual-only, commissioning off, commands 0, encoders unchanged; telemetry ≤ 0.3 s; CPU 62.4 %, RAM 63.6 %, 63.1 °C |
| Monitoring | Prometheus `up` ratio 1.0 over the last 8 min; CPU max 63.0 % |

The original watchdog fault cause remains **UNKNOWN**. Its evidence is kept in the attempt 1–5 archives. Reboot persistence is unverified.


## Attempt 4 result and attempt-5 preparation (2026-10-31; offline; NOT executed)

**Attempt 4** (`-20261031-4`, 14:06:42 – 14:11:53) was **FAIL; cleanup VERIFIED**.
- Prometheus and Grafana were healthy for the whole window.
- At 14:11:50.32 `failure.json` recorded a missing `client-confirmation.json`.
- The sudo log shows `confirm-client` (and `sudo -v`) were never run.
- There was no watchdog rejection. `FAULT.json` remains `3715b150…ae97`.

**Owner-read state after attempt 4** (`sudo`, 14:18). Hashes were recomputed from the printed bytes:

| File | SHA256 | Provenance |
|---|---|---|
| `FAULT.json` | `3715b150…ae97` | Original latch; restored 14:11:51.885 |
| `firewall-owned.json` | `595bc54f…4cf7` | Attempt-4 firewall start, 14:06:48.798 |
| `last-health.json` | `93ecbdad…6886` | Attempt-4 watchdog, 14:11:48.254 |
| `rollback.json` | `84ff1598…2c78` | Attempt-4 cleanup, 14:11:51.562 |
| two lock files | empty | Unchanged |

Attempt 4's manifest equals the attempt-4 verified state. Its archived `FAULT.json` is the original, and its `result.json` is `235d2a6e…` (FAIL / VERIFIED).

**Change (`recover_once.py` only):**
- New identity `-20261031-5`.
- The expected state is exactly the table above. Attempt 4 is chained into the lineage check (manifest, archived latch, result).
- `start` now prints a **target** confirm time (start + 120 s) as well as the latest time (start + 240 s).
- No bound, check, threshold, firewall, watchdog or rollback change.

**Validation:** 52/52 transaction tests pass under both UTC and IST, including 10 lineage and tamper cases across attempts 1–4.

**Package:** `monitoring-recovery-transaction-20261031-5.tar.gz`, SHA256 `c02117e10df7786ccecb971972a7d3b21caabb93cf96a6029aaae7daa88fb974`. Manifest `1cf14aea…1066`; `recover_once.py` `62587e22…120c`.

### Attempt-5 operator procedure

1. **Before starting:**
   - Log in to Grafana (**ATLAS HEALTH MONITOR**) and the Prometheus targets page.
   - Claude runs a fresh read-only safety preflight and reports GO.
2. **Terminal 2 (Jetson):**
   - Run `sudo -v`.
   - Type `sudo /usr/bin/python3 -I -B /opt/atlas-monitoring-recovery-20261031-5/recover_once.py confirm-client`. **Do not press Enter.**
3. **Terminal 1 (Jetson), after separate approval:** run the single `start` command. Read the printed **target** and **latest** times.
4. **Watch Prometheus and Grafana yourself.**
   - Prometheus: target `up`, recent "last scrape", no error.
   - Grafana: values updating, E-STOP LATCHED, missing data shown as UNAVAILABLE.
5. **When both pass, press Enter in Terminal 2 immediately**, around the target time (start + 2 min). **Do not wait for a chat message.** Never press it after the printed latest time.
6. If either check fails, do not confirm. The transaction cleans up by itself. Never re-run `start` or `confirm-client`.


## Attempt 4 preparation (2026-10-31; offline; NOT executed)

**Owner-read state after attempt 3** (`sudo`, Jetson, 13:57). Every hash was recomputed from the printed bytes:

| File | SHA256 | Provenance |
|---|---|---|
| `FAULT.json` | `3715b150…ae97` | Original latch, byte-identical; restored at 13:25:23.877 |
| `firewall-owned.json` | `9a99129e…ffb5` | Attempt-3 firewall start, 13:20:20.922 |
| `last-health.json` | `d8420183…134f` | Attempt-3 watchdog, 13:25:20.215 |
| `rollback.json` | `9983f96f…4a6e` | Attempt-3 cleanup rollback, 13:25:23.582 (`PASS`) |
| `evidence.lock`, `operations.lock` | empty | Unchanged |

- Nothing in the folder is newer than 13:25:23.877.
- Attempt 3's `state-manifest.json` equals the 13:15-verified state.
- Attempt 3's archived `FAULT.json` is `3715b150…`.
- Attempt 3's `result.json` is `235d2a6e…a045` (FAIL / VERIFIED).
- `-20261031-4` is unused.

**Change (`recover_once.py` only):**
- New identity `-20261031-4`.
- The expected state is exactly the table above.
- The lineage check now also requires:
  - attempt 3's archive manifest equals the state it archived;
  - its archived `FAULT.json` is the original latch;
  - its result is pinned by hash.
- `start` prints the window close time and the confirm-by time (start + 240 s).
- The window, deadlines, expiry, archive-before-reset, firewall, watchdog, rollback and the 75 % / 80 % / 70 °C limits are unchanged. The original cause remains UNKNOWN.

**Validation:** 49/49 transaction tests pass under both UTC and IST. They cover the attempt-2 refusal, 8 lineage and tamper cases (attempts 1–3), the pinned attempt-4 state and the confirm-by message. The deadline test also checks that the 300 s window and 410 s expiry are unchanged.

**Package:** `monitoring-recovery-transaction-20261031-4.tar.gz`, SHA256 `b6698307e2c2c8619d2055a2ecbbadc0cd671bf0c1dce41ce304a4e7f6ecb1d0`. 8 members, root:root 0644; manifest `cc1896cc…0812`; `recover_once.py` `e1fb74c8…3781`.

## Attempt 3 result (2026-10-31; FAIL, cleanup completed; no attempt 4 built)

**Cause: the owner confirmation arrived after the 300 s window closed.** The transaction behaved as designed.

| Time (IST) | Event (Jetson journal and sudo log) |
|---|---|
| 13:20:14.8 | `start` (worker started 13:20:15) |
| 13:20:20.7 / 23.9 / 27.6 | Firewall / watchdog / exporter started. The window runs from the firewall start to about **13:25:20.7**. |
| 13:20:30 – 13:25 | Prometheus target `up`, 221 series, no stale topics, E-STOP = 1. The owner confirmed live Grafana data. |
| **13:25:22.36** | **First failure:** the worker's final check found no `client-confirmation.json` (`FileNotFoundError`); exit 1 |
| 13:25:23.4 | Exporter, watchdog and firewall stopped cleanly ("Deactivated successfully") |
| 13:25:25.58 | Expiry cancelled. This happens only after cleanup records `FAIL / VERIFIED` and restores the latch. |
| 13:25:56.23 | `confirm-client` ran, 34 s too late; refused with `fault latched` (latch already restored) |

- **No independent watchdog rejection.** The watchdog stopped cleanly. A rejection would have latched a new fault and ended the worker early.
- **Final state:** monitoring units inactive, no drop-ins, exporter enable state and restart policy restored, no 9118 listener, no recovery units. The `-3` folders are kept; the attempt is consumed.
- **Monitoring UNAVAILABLE afterwards is expected:** the exporter is stopped. The rover's own status at 13:28 showed E-STOP latched, encoders READY and stationary, and all topics fresh.
- **A future `-4` needs a fresh owner `sudo` read of `/var/lib/atlas-monitoring`,** because attempt 3 legitimately rewrote its firewall-owner, health and rollback records again, plus attempt 3's `result.json` pinned. Not built.

### Operator checklist for any future attempt

1. Claude runs a read-only preflight and reports GO: E-STOP latched, manual-only, commissioning off, zero commands, stationary encoders, fresh telemetry, CPU < 75 %, RAM < 80 %, temperature < 70 °C, attempt unused.
2. Open **two** Jetson terminals. In terminal 2, run `sudo -v` first, so no password prompt costs window time.
3. In terminal 2, type the `confirm-client` command but **do not press Enter**.
4. Open Grafana (`http://127.0.0.1:3000`, logged in) on **ATLAS HEALTH MONITOR**.
5. In terminal 1, run the single `start` command. It prints the window close time and a **confirm-by time** (start + 240 s). Tell Claude "started".
6. Within about 60 s, Claude reports the Prometheus result: target up, fresh samples, valid timestamps, missing data shown as UNAVAILABLE.
7. Once Grafana shows live data, press Enter in terminal 2. **Deadline: start time + 4 minutes.** The hard limit is about 5 minutes after the firewall starts.
8. If anything fails, do nothing: the transaction cleans up itself. Never re-run `start` or `confirm-client`.


## Attempt 2 result and attempt-3 correction (2026-10-31; offline; NOT executed)

**Attempt 2** (`-20261031-2`, 12:57:21 IST) was **FAIL before any change**. The worker refused in `archive_state()` with `retained evidence changed`. No `mutation-intent.json` was written, the latch and firewall were untouched, and no unit started. `result.json` = `{"cleanup": "NO_MUTATION", "result": "FAIL"}`; the expiry fired at 13:04:11 and recorded the same result. Its directory is retained evidence and is never reused.

**Cause:** the expected-state list was the snapshot from *before* attempt 1. Attempt 1 legitimately changed the folder before its verified cleanup, which restored only `FAULT.json`. The readiness review verified `FAULT.json` alone and did not flag that the other root-only hashes were unverified.

**Owner-read state** (`sudo`, 13:15, `/var/lib/atlas-monitoring`). Every hash was recomputed from the printed bytes, and the content times lie inside attempt 1:

| File | SHA256 | Provenance |
|---|---|---|
| `FAULT.json` | `3715b150…ae97` | Original latch, byte-identical (content time 10-31 09:34:08). Restored by attempt 1's cleanup at 11:40:08. |
| `firewall-owned.json` | `5f3fe2b4…648b` | Attempt-1 firewall start, 11:39:59.555 |
| `last-health.json` | `8e918d71…aa7f` | Attempt-1 watchdog start, 11:40:02.572 |
| `rollback.json` | `3bc4ba22…204e` | Attempt-1 cleanup rollback, 11:40:07.851 (`result: PASS`) |
| `observer-active.json` | absent | Removed by attempt 1's clean watchdog stop |
| `evidence.lock`, `operations.lock` | empty | Unchanged lock files |

Nothing in the folder is newer than 11:40:08, so attempt 2 changed nothing.

**Correction (`recover_once.py` only; nothing else in the package changed):**
- New identity `-20261031-3`.
- `VERIFIED_STATE` holds exactly the hashes above. `FAULT.json` must equal the original latch hash; an extra, missing or changed file is refused.
- `verify_lineage()` runs before archiving. Attempt 1's archive manifest must equal the pre-attempt-1 state (plus its empty `evidence.lock`). Attempt 1's archived `FAULT.json` must match the original hash. Attempt 1's `result.json` (FAIL / cleanup VERIFIED) and attempt 2's (FAIL / NO_MUTATION) are pinned by hash. Attempt 2 must have no `mutation-intent.json`.
- The reset removes `observer-active.json` only if it is part of the verified state.
- The startup deadlines, supervision, expiry, cleanup, firewall and rollback are unchanged.

**Validation:** 45/45 transaction tests pass, including the attempt-2 reproduction with 6 tamper cases and the pinned constants. The 4 native systemd tests still apply: the launch command is unchanged.

**Package:** `monitoring-recovery-transaction-20261031-3.tar.gz`, SHA256 `d165261bc878a37bc48323fba88b65c1d33945ab71a3c90f5ca3584285e6fc20`. 8 members, root:root 0644; manifest SHA256 `8c5ac7d31fc436c0aad894aed0c80a97c7447ef9765182730b7485272eb05dfe`; `recover_once.py` `7d038f36…596e`. Use only the `-20261031-3` commands below.

## Correction for attempt 2 (superseded by attempt 3): startup deadline and launcher stop only (2026-10-31, offline; NOT executed)

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

**Final readiness check (2026-10-31 11:48–11:52, read-only):**

| Item | Result |
|---|---|
| Archive SHA256 | `b997bcd4…c167` on the PC and on the Jetson (`~/project-atlas-migration/`, copied only) |
| Archive members | 8, each byte-identical to the repo |
| Command sections | Use only `-20261031-2` (staging, run, confirm, abort, rollback); attempt-1 history is unchanged |
| Code identity | `E`, `TX` and the expiry derive `-20261031-2`; the attempt-1 directory is never referenced |
| Attempt-1 evidence | Present (root 0700) |
| Monitoring | Units inactive (exporter enabled), no 9118 listener, no recovery units or timers, guard 27d4cacae470 |
| Rover | E-STOP latched, manual-only, uncommissioned, source STOPPED, XBOX; cmd 0, motor 0; encoders still for 6 s [114,-137,-155,-178]; required topics fresh |
| Resources | CPU 62.4 / 64.5 / 61.3 %, RAM 62.2 %, 62.1 C |

- **Attempt-1 leftovers:** empty root-only `atlas-monitoring-{exporter,watchdog,firewall}.service.d` directories in /run/systemd/system. Systemd reports no DropInPaths. The transaction's `configurations()` check (DropInPaths) and `prepare_override()` (file `lexists`, `mkdir exist_ok`) accept them. Not a blocker; tmpfs, gone at reboot.
- **PENDING:** the 4 native fake-systemd tests. The WSL and Windows hosts are not reachable from this session (sandbox VM without systemd). Run them on the PC before execution.


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

## Exact execution sequence — attempt 5 (`-20261031-5`); NOT authorized by this document

Approval must cover: one archival/reset accepting UNKNOWN original cause; optional
monitoring starts; temporary monitoring-only Restart=no/system daemon-reload;
temporary exporter disable/restore; expiry cleanup and the revised ~440 s bound.
Administrator passwords belong only in the local Jetson terminal.

1. Confirm the approved package tar/manifest hashes against the review report.
   Copy the verified extracted seven files plus manifest to the new root-owned
   directory `/opt/atlas-monitoring-recovery-20261031-5` (0755 directory, root:root
   files 0644). Do not reuse an existing directory or overwrite installed files.
   Installation of this transaction package does not start a service.
   Once the separately approved copy is at the path below, exact staging is:

   ```sh
   cd /home/jetson/project-atlas-migration &&
   printf '%s\n' 'c02117e10df7786ccecb971972a7d3b21caabb93cf96a6029aaae7daa88fb974  monitoring-recovery-transaction-20261031-5.tar.gz' | sha256sum -c - &&
   sudo /bin/sh -c 'set -eu; umask 022
   mkdir /opt/atlas-monitoring-recovery-20261031-5
   tar --no-same-owner -xzf /home/jetson/project-atlas-migration/monitoring-recovery-transaction-20261031-5.tar.gz -C /opt/atlas-monitoring-recovery-20261031-5
   cd /opt/atlas-monitoring-recovery-20261031-5
   sha256sum -c RECOVERY_SHA256SUMS'
   ```

   A pre-existing target directory aborts staging. Do not remove it to force a
   retry. Confirm all files are root:root/0644; `load()` rejects writable files
   or ancestors. The archive is hash-checked before its root extraction.
2. With the owner present and the rover stationary, run **once** locally:

   ```sh
   cd /opt/atlas-monitoring-recovery-20261031-5 &&
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
   sudo /usr/bin/python3 -I -B /opt/atlas-monitoring-recovery-20261031-5/recover_once.py confirm-client
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
sudo systemctl stop atlas-monitoring-recovery-once-20261031-5.service
```

If cleanup reports FAILED, do not repeat `start`, remove evidence, reset-failed,
flush rules or manually start the exporter. Inspect the local result and journal.
After confirming the transaction worker and its cleanup have exited, the reviewed
monitoring-only manual rollback is:

```sh
sudo /usr/bin/python3 -I -B /opt/atlas-monitoring-recovery-20261031-5/guard.py rollback &&
sudo /usr/bin/python3 -I -B /opt/atlas-monitoring-recovery-20261031-5/recover_once.py cleanup
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
