# Corrected Recovery restoration result — 2026-10-31

Approved package 295dba6, manifest SHA256
48ee833a362f37732586548b0e35b6fcd83678bf72457f0e95071f27bf92307b.
All nine files and both original Recovery hashes verified. Exactly one start,
no retry. RESULT FAIL: real CPU_LIMIT rejection at 86.934673%, not scan timeout.
Incident remains OPEN; Recovery is STOPPED.

## Timeline (IST, Oct 31)

- 09:03:42 supervisor PID 374038 started.
- 09:03:43–45 preflight CPU 61.87%, 58.42%, 60.10%; safety gates passed.
- 09:03:46–48 observer CPU 67.23%, 59.09%, 61.15%; gates passed.
- 09:03:49.74 sample 63.65%; start intent at 09:03:49.869.
- Recovery PID 374161, birth tick 5863526; one start only.
- 09:03:50.75 sample 66.28%.
- 09:03:51.555 Recovery logged READY: full bounded fault recovery armed.
- 09:03:51.75 sample 86.934673%: rejected, evidence saved, cleanup started.
- 09:03:52 Recovery stopped. Lifetime cgroup CPU 1.697 seconds.
- 09:03:53 supervisor failed, cleanup recorded RESTORED / STOPPED / one attempt.

READY briefly appearing is not a successful restoration: safety acceptance failed.
All nine sample scans were complete; rejected scan took 42.96 ms and its aggregate
interval was approximately 1.00 s. The corrected persistence path retained the
actual rejected CPU endpoint and process/cgroup counters. No partial scan occurred
in this run; partial behavior remains covered by offline tests.

## Attribution, not an unsupported causal claim

Rejected interval cgroups (% of ONE core):
- Recovery 54.71 (0.552294 CPU seconds / 1.009524 wall seconds).
- Localization 48.22, versus 16.80 in the preceding interval.
- Dashboard 32.88, versus 38.54 previously.
- Command mux 19.73, versus 17.32 previously.

Recovery PID measured 54.48% of one core; do not add PID and its cgroup together.
Collector PID 374087 used 4.93% of one core; supervisor PID 374038 used 0.99%.
Other busy PIDs include base telemetry 26.62%, existing Pi Camera 24.64%, voice
19.72% of one core. This was not Astra activation.

Confirmed: genuine aggregate overload coincided with Recovery initialization and
higher localization CPU. Collector timing was valid and no longer erased evidence.
UNKNOWN: specific hot ROS/DDS functions and complete causal explanation for 86.93%
whole-machine CPU. Sequential process/cgroup windows are not identical to aggregate
endpoints, and missing/exited work cannot be assigned an exact residual cause.
A single rejected sample does not prove sustained overload or a harmless transient.
No restart, optimization or safety-limit exemption is recommended without reviewing
this saved interval; no new profiling framework was created.

## Final verification and cleanup

- Recovery MainPID=0, inactive, NRestarts=0, Restart=always, no pending job.
- Original live and rollback source hash still
  5f44cc1fbd7cdc65b8af17abeb9ecd41cec0a8c8f3ee8274fa9b34362633193a.
- Original unit text and final text match exactly.
- Temporary owned Restart=no override and diagnostic runtime unit removed.
- 41 unrelated service PID/state/restart-count/cgroup identities unchanged.
- Snapshot producer disabled; Astra OFF verified by existing authoritative check.
- Postflight CPU 60.5863%, RAM 62.3822%, maximum temperature 62.406 C.
- E-STOP latched, commands zero, encoders stationary, LIVE telemetry age 0.036s.
- No camera/inference/mapping activation, movement, firmware write or PR merge.

Evidence retained on Jetson:
/home/jetson/project-atlas-migration/recovery-restoration-1d81445
Private PC copy: work/recovery-restoration-result-20261031 (outside repository).
EVIDENCE_SHA256SUMS verified remotely and on the downloaded copy. A trailing CR in
an initial evidence-manifest filename caused a copy failure; only that manifest
filename/list was corrected and reverified. No measurement or runtime was repeated.
Raw private telemetry is not committed. Attempt marker and complete evidence retained.