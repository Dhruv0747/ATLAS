# Recovery CPU attribution: guarded isolated test preparation — 2026-10-31

Base d7370f4. OFFLINE ONLY. Recovery's last verified state remains STOPPED.
No Jetson command, transfer, service operation or live test was performed here.

## Verdict

GO for ONE separately approved passive Jetson overhead test, subject to fresh
preflight and verified package staging. NOT approval to start Recovery. The
93.624% historical startup cause remains UNKNOWN; prior attribution gaps cannot
be repaired by offline simulation. Restoration remains the priority incident.

## Implementation

Added recovery_attribution_trial.py, test_recovery_attribution_trial.py and
build_recovery_attribution_package.py. Existing collector and production safety
predicate modules are reused unchanged. No changes to original Recovery, staged
backend, ROS, controllers, camera, systemd policy or firewall.

The parent takes three one-second baseline safety samples, starts an independent
child for12one-second samples, then takes three after-test samples. All use the
same /proc attribution and existing E-STOP/manual-only/zero-command/stationary-
encoder/LIVE fresh telemetry/resource predicates. HTTP is supplied by the existing
Dashboard, independent of Recovery; HTTP failure aborts. This is NOT approved for
Dashboard downtime and must not be reused as a web-restart observer.

The child receives the LAST baseline endpoint. No CPU counter reset discards its
interpreter/import startup. Every sample contains raw process/group counters and
monotonic boundaries. On rejection, health is marked FAILED first, then the full
rejected sample is atomically persisted. The parent allows at most300ms for that
failed child's evidence write before termination. No HTTP/thermal requests follow
an already failed CPU test. Durable completed files survive SIGKILL. SIGKILL or
storage failure during a write can still lose that incomplete sample; .tmp files
are not valid completed evidence and no final result means NOT PASS.

Process/cgroup endpoints are sequential (collection budget150ms), not simultaneous.
New PID lifetime counters are labeled cumulative; disappearing processes and
missing/recreated groups remain explicit gaps. A first-second process that exits
between samples cannot be attributed exactly. Cgroups are resolved ONCE from actual
systemd ControlGroup and /proc/self/mountinfo, not rediscovered per PID. A stopped
Recovery group may be absent and is recorded as such. Do not sum nested groups or
label residual CPU as exact kernel/scheduler work.

The parent polls child health every20ms and rejects missing/stale observations
older than1.8s, malformed health, failed child or missing successful completion.
The child has a15s parent deadline,3CPU-second limit,128MiB address-space limit,
16MiB per-file limit and64FD limit. Parent address space is256MiB. Collector evidence
quota is16MiB. Normal sampling is1Hz; scheduling intervals outside0.9–1.1s fail.
The external timeout is30s, TERM then KILL after2s if necessary. This is bounded
best-effort Linux scheduling, not a hard real-time abort guarantee.

PDEATHSIG kills ONLY the diagnostic child if its parent dies, including SIGKILL.
The expected parent PID is captured before fork and rechecked after prctl, closing
the pre-exec parent-death race. Native tests verify this. Normal cleanup TERM/waits
0.5s then KILL/waits0.5s and reaps only the owned child. No service commands except
read-only systemctl show exist in the wrapper. No ROS/DDS participant is created.
ATTEMPT_USED prevents an automatic or accidental second run of the package.

## Focused tests and measured PC overhead

13 new focused cases PASS: rejected first interval preserves exact PID counters;
missing/exited PID; HTTP timeout/missing/stale observer data; invalid time interval;
missing child heartbeat; missing completion; native supervisor SIGKILL child cleanup
and durable evidence; temperature boundary; E-STOP/command/telemetry/RAM failures;
v2 cgroup resolution with absent Recovery group; hash tamper rejection; parent-death
race; full native18s wrapper lifecycle with simulated safety/service responses.
Prior11collector tests from d7370f4 are reused, not repeated.

The full native WSL Ubuntu22.04 rehearsal uses REAL /proc sampling, child interpreter,
resource caps, parent monitor and atomic filesystem persistence. Safety HTTP,
thermal readings and service identities are simulated; NO actual services touched.
Latest measured run:
- First window1.000972064s; no startup counter reset.
- Child cumulative CPU through first sample0.050609549s (includes interpreter/imports).
- Child cumulative CPU through12th sample0.090191172s (~0.752% one core over12s).
- Peak child RSS21136KiB (20.64MiB).
- Result PASS, child reaped, no production change.
Earlier identical rehearsal0.089156471CPU-s/21144KiB corroborates magnitude, not a
Jetson guarantee. Actual HTTP latency, parent CPU and total host overhead must be
measured in the isolated Jetson test. Do not interpret these as Recovery CPU savings.

Reproduce focused tests on PC from project_atlas/tools/vision3d:
`python3 -m unittest test_recovery_attribution_trial -v`
No fake services, native service restart or ROS process is required.

## Prepared package

PC-only directory (not staged to Jetson):
C:/Users/Dhruv/Documents/Codex/2026-07-24/h/work/recovery-attribution-prepared-20261031

Build reproducibly with build_recovery_attribution_package.py <new-directory>.
Builder normalizes LF/UTF-8, copies only six required Python files, writes SHA256SUMS
and refuses an existing destination. Manifest SHA256:
fe5b945f6df055358a9ab5e05b1428b2559a175c1876f8bd408f179069a587a3

Files and hashes:
- recovery_attribution_trial.py:237b62f55f57098756385c745744246e5708bc3b19aea9cc0ada373199df1028
- startup_cpu_attribution.py:d3bdbe448d1e7a84796063d5c6d9f1a9ca208b5d81681c6f4dcfd26fecc911f0
- snapshot_benchmark_once.py:2a91731b49447c752df7d0c9d6710b862c692c5bfc8ee2231e64d6f5769298ae
- stationary_gate.py:0c5ec244b238aa741f3dc2d6fe7c7f588fdd3511e2a3e2c7c36f2ab355a5bfe9
- install_verification.py:d2f4cc655d0562a696c498ee5f2e79501b4cae7667a7b8a97f71f53cd36126c1
- restart_policy.py:5efcba6d7b6f22c238673f62bde75b99b1be43308d7fa19c1a09027666d26ad3

## Future procedure — separate approval required; DO NOT RUN NOW

Approval scope: copy this package into a NEW non-production staging directory and
run ONE isolated read-only overhead test as jetson user. No sudo needed normally;
permission-denied evidence is reported, never worked around by privilege escalation.

Before launch verify package, Recovery PID0/stopped, snapshot output not enabled,
protected service health, Dashboard HTTP available and Astra OFF. Keep E-STOP
latched, actuators isolated and rover stationary. Built-in three-sample preflight
requires CPU<75%, RAM<80%, all trusted thermal zones<70C and fresh safe telemetry.
During capture CPU>75%, RAM>80%, temperature>=70C or any other safety failure aborts.
No resource exception, averaging or retry is allowed.

After approval and staging to the named NEW directory only:
```sh
cd /home/jetson/project-atlas-migration/recovery-attribution-isolated-20261031 &&
printf '%s\n' 'fe5b945f6df055358a9ab5e05b1428b2559a175c1876f8bd408f179069a587a3  SHA256SUMS' | sha256sum -c - &&
sha256sum -c SHA256SUMS &&
env -u PYTHONPATH -u PYTHONHOME /usr/bin/timeout --signal=TERM --kill-after=2s 30s /usr/bin/python3 -B recovery_attribution_trial.py --approved-once
```
Do not run an older recovery-start script. The above directory does NOT yet exist
on Jetson as a result of this work. No automatic retry if admission fails.

## Exact cleanup and rollback

Normal/failure/interruption: wrapper terminates/reaps only its owned diagnostic
child, retains evidence/result.json and SHA256SUMS. Ctrl+C once invokes this cleanup.
Supervisor SIGKILL: kernel PDEATHSIG kills its child; completed evidence persists,
final result/manifest may be absent. Treat as aborted, never infer success from a
leftover safe health file. A briefly unreaped zombie is not a running collector.

Read-only verification after exit (from that staged directory):
`cat evidence/result.json; (cd evidence && sha256sum -c SHA256SUMS)`
If result/manifest is absent, preserve files and check the recorded child PID AND
/proc/PID/stat start_ticks against evidence/owned-child.json; do not kill a reused
PID. Report crash/ABORT and retain completed numbered JSON for offline checksum
reconstruction. Never use killall/pkill or restart Recovery as diagnostic cleanup.
Recheck original service identities and Recovery PID0 after interruption; no live
claim can be made from this offline test.

There are NO production changes to roll back: no installed service, config, policy,
producer opt-in or driver modification. Keep package/evidence and ATTEMPT_USED;
do not delete them to rerun. No restoration restart belongs to this procedure.

## Remaining restoration blockers

- Actual Jetson collector+guard+HTTP overhead and gaps not yet measured.
-93.624% cause and sustained/transient nature still UNKNOWN.
- This integration observes independently of Recovery but has no restart actuator.
  A future restoration approval must separately validate one-start/fail-closed
  integration with this retained evidence, not reuse this passive command to start
  a service.
- Central recovery functionality remains unavailable; independent E-STOP/mux/base
  watchdog paths are not substitutes for full sensor recovery. No motion acceptance.

No new restart is proposed until the passive overhead evidence is reviewed. All
limits, original files and working Dashboard remain unchanged.
