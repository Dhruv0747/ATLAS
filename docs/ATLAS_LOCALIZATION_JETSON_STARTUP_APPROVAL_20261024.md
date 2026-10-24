# Guarded isolated Jetson startup package — approval required

## Status

Prepared locally only. NOT copied to Jetson, installed, or executed. No SSH,
camera, movement, production restart or new ROS participant this turn.
24 offline tests pass on Windows;5 package tests also pass under Linux/WSL.
All10 packaged file hashes independently verified. Generated worker compiles;
no ARM64/ROS test was run. Initial Windows mock failure (os.killpg absent) was
fixed in the test only; superseded v1 bundle retained, not approved.

## Exact package

Local archive: `artifacts/localization_startup_approval_20261024_v2.tar.gz`

- Archive SHA256: `16032598eef40ef6c919b2e182b5a0fe03329ae661330ceada3d091e9543ab2f`
- Manifest SHA256: `8c52758413d1b671d1df2edf569106343447f23ba3c1888bbbd325d1888376bc`
- Supervisor SHA256: `ddf34836d9efbaafbf42bb855ca006a746374e4c98e4b18464df3dcbe3e415c7`
- Worker SHA256: `657271a3c14df63302120c37218e9646fc2a84017d815eb95103fb3d50caa14f`

Manifest pins copied monitor/manual/core source, support modules, local saved
map and executable diagnostic files. Production expected hashes include monitor,
core, manual check, Dashboard, voice, safety reporter and white-glass CSS;
supervisor separately pins stationary guard/probe. Any mismatch aborts, never
automatically updates the expected hash. Local map is a fixture, not proof of
current production-map identity. No raw production files overwritten.

## Approved workload requested (ONE test)

1. After explicit approval, copy archive to a NEW isolated diagnostic directory;
   verify archive and manifest against this report before execution.
2. Verify production/package/guard hashes, at least512MiB free disk and protected
   services active. Exclusive trace creation prevents reusing the run directory.
3. Collect10 one-second baseline safety/resource samples. Enforce CPU75%,RAM80%,
   temperature70C, E-STOP latched, manual-only, zero commands, recorderOFF,
   commissioning disabled, required sensor freshness and AstraOFF. Existing
   USB-access verification remains part of the unchanged probe.
4. Start exactly ONE original-constructor worker in private localhost domain214
   with an isolated HOME, fixture map and copied sources. Strip external DDS
   discovery/profile configuration. Production domain and Astra domain77 unchanged.
5. Keep application node unspun, cancel its timers, block service calls. Only
   synthetic1Hz heartbeat publisher/subscriber nodes spin. Initial diagnostic
   status file writes go only into isolated HOME. No actual mission commands.
6. Monitor resources and existing Dashboard receipt data at1Hz. Snapshot retains
   mission age, sample_time, observed_hz and READY predicate, plus sensor ages.
   Never refresh a failed sample merely to obtain a pass. Resource interval and
   safety-query duration each must remain <=1.5s.
7. Worker has20s supervisor deadline; actual termination includes next sampling
   boundary and bounded owned-process cleanup. SIGINT then SIGKILL only to its
   process group (2s waits each). No retry, service restart or CPU override flag.
8. Recheck production hashes, safety and protected service identities afterward,
   including mission control and localization monitor. Even if final resource
   check fails, still attempt service identity reporting; mark result ABORTED.

## Evidence / interpretation

Persistent stage BEGIN/completion entries include monotonic time, process CPU,
native thread ID, RSS, scheduler runtime/wait counters and cgroup membership.
BEGIN entries survive a stop before a stage completes. Counter reads that fail
are UNKNOWN. Cgroup throttling is explicitly UNKNOWN: no production CPUQuota or
Nice setting is cloned/modified. This test adds bounded work to the already
loaded Jetson; it may abort at admission or during construction.

CPU measurement remains one-second, not averaged to hide peaks. Diagnostic
trace writes and monitoring add overhead; results are not a deployed CPU-saving
comparison. Synthetic heartbeat and Dashboard production receipt ages belong to
different paths. Neither proves the actual production publisher timing.

Pass requires all guard samples, complete construction/destruction, synthetic
message accounting, no leftover child, unchanged protected services/hashes.
No-staleness result means NOT REPRODUCED, not FIXED. Reproduction with stage
timings narrows the cause; exact publisher-versus-DDS-versus-Dashboard attribution
may still need separate narrowly scoped instrumentation approval.

## Cleanup, rollback and boundaries

No production installation: rollback is terminating the owned worker. Preserve
result.json, guard-trace.jsonl, worker-stages.jsonl, worker output and isolated
status files. Never delete older evidence. No autostart, camera/bag recording,
calibration, map, steering, voice, white-glass or safety-policy changes.

Source changes: localization_startup_jetson.py, package_localization_startup.py,
test_localization_startup_package.py plus this report/audit records. Tests cover
strict CPU rejection, manifest path escape/hash mismatch, safe stopped-process
handling, generated worker scope/compilation and retained supervisor protections.
They are not full end-to-end ARM64 failure-injection qualification.

## Exact next owner approval

Approve copying this hash-verified v2 bundle to a fresh Jetson diagnostics folder
and running ONE guarded isolated startup test under the unchanged75/80/70 limits,
with no production installation/restarts, camera, recording or motion. Abort on
any failed check and do not retry. Previous CPU-report-only exceptions do not
apply. Approval is pending; the manifest intentionally says NOT APPROVED TO RUN.
