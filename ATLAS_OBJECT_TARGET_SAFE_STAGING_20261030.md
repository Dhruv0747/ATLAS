# Safe backend staging — PASS; activation remains blocked

Owner authorized non-activating staging only. Reviewed52d6b15 backend plus7dba9bd
offline installation verification package copied to:
`/home/jetson/project-atlas-migration/object-target-staged-7dba9bd/review/`.
Nothing was copied into the live application. No installer was executed.

Outer manifest SHA256:
`a586c2d22276ef4f7385387a79cadd581b2c7a52567d89a8754ee051b9c99e68`.
20 manifest entries verified on both PC and Jetson. Three rollback originals match
the actual live files byte-for-byte. Staged config remains enabled=false.
Existing detector, TensorRT engine and stationary guard hashes match the reviewed
preparation report. NumPy, cv2 and TensorRT module locations exist on Jetson; no
engine deserialization or inference was performed. Actual inference compatibility
remains unverified.

Focused offline PC check: all four feature modules imported, no additional thread,
no active Lab session. Jetson staged Python files parse successfully without
execution. Existing13 verifier tests and2 staging/import tests reused unchanged.

Live homepage/backend/preview JS/material stylesheet hashes unchanged. All observed
atlas-/rover- service identities, active states and restart counts match before/after
staging. Web PID182915, NRestarts0. Existing HTML retains24 disabled controls.
Camera summary remains OFF; its known raw driver_stopped=false idle representation
is preserved, not relabeled as an affirmative driver-stop signal. No camera or AI
activation command was issued. No browser behavior or live UI code changed.

Private Jetson evidence: adjacent before.json and result.json. Exact rollback
copies are in review/package/rollback. Since no live file was changed, staging
rollback requires no web restart or live restoration: discard only this verified
staging directory if desired. Do not execute the installer as part of cleanup.

## Remaining activation blocker and future policy gate

Existing journal/Grafana evidence reviewed, with no new capture:79.1453% occurred
during old-web shutdown; no per-process deltas attribute it.39/39 Prometheus
scrapes failed in the surrounding10min, so no historical CPU trend resolves its
duration. See ATLAS_WEB_SHUTDOWN_CPU_ASSESSMENT_20261030.md. Cause UNKNOWN.

The current backend is imported at web startup, so staging alone cannot expose
new APIs. One web-only restart is technically sufficient; no protected ROS or
controller restart is needed. Safety of that restart is NOT established.

Any future restart proposal needs bounded low-overhead process/cgroup attribution,
PID/starttime identities, synchronized one-second aggregate CPU counters, pre-stop
baseline, shutdown/start/readiness/rollback timestamps and continuous resource
evidence. Independent safety observation during the web API outage must be reviewed
before execution; missing/stale safety must not be declared PASS. Preserve controls,
telemetry and existing safety services. Stop on guard failure; no automatic retry.

CPU75% remains mandatory. No transient policy is implemented or presumed approved.
A separately proposed transient policy would need evidence for worst-case control,
E-STOP and telemetry deadlines plus explicit duration/ceiling/abort/rollback terms;
those cannot be justified from the saved aggregate sample. Owner approval alone
must not be misrepresented as proof of timing safety. No numeric exception is
proposed here, and no production guard may be relaxed under this staging approval.

Verdict: PASS for safe staging; NO-GO for automatic activation or live AI testing.
Next authorization, if pursued, must separately cover a reviewed bounded diagnostic
restart/observer plan. Do not rerun any consumed installation attempt.
