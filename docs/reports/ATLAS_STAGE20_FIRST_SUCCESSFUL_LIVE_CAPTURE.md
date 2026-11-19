# First live30s attempt — NOT SUCCESSFUL

14 October2026,23:02 IST. Filename follows owner request, not a success claim.
**PREFLIGHT PASSED / RECORDING INCOMPLETE (startup aborted; no bag created).**
One authorized attempt only. No retry or threshold change.

Exact supervisor and installed capsule hashes matched. Required sensor topic probe
received scan65, EKF82, wheel odom85, corrected IM10A88, TF142, encoder updates84,
each wheel82, AMCL9, particles8, staticTF2; none missing. These are preflight probe
counts, NOT recorded bag messages. Continuous receipt ages <0.11s. Stop latched,
zero commands, commissioning false, Nav2/explore inactive; no existing grant.

Independent five preflight CPU intervals:71.3568,69.3739,69.8653,70.2886,68.6644%.
Preflight passed unchanged75% policy. One new grant created; optional recorder start
requested once. First subsequent1.000807s CPU interval was **76.22950819672131%**.
Exact rejection at17:32:12.056957UTC (23:02:12IST), field cpu_samples[0], limit75%.
Cached dashboard CPU70.0%, RAM67%,58C,394310217728 free bytes. Cached resource age
not provided by dashboard, recorded UNKNOWN; not substituted with HTTP receipt age.
Supervisor invoked stop ONLY on the optional recorder. Grant revoked, no retry.

Six independent observed CPU intervals (five preflight + one after start):
mean70.9631%, nearest-rank p95/peak76.2295%. During startup only one interval exists;
its mean/p95/peak are all76.2295%, not a30s workload benchmark. Recorder CPU/peak RAM
were not captured before this early termination: UNKNOWN. Do not attribute the
whole-system spike exclusively to the recorder without process measurements.

Systemd journal confirms start at23:02:10–11 and stop at23:02:12. No bag directory
or receipt ledger was created; actual data receipt window did not begin. Recording
size0 bytes, recorded messages0, no capture SHA256. SQLite/CDR integrity, source
continuity, callback/writer delays, drops and DDS loss cannot be assessed. No false
zero-loss or live-capture pass claimed. Process-start intent flags in supervisor
are conservative, not an independent process CPU/duration measurement.

Exact rejection sample, timing, threshold, traceback and final report survived:
`/tmp/atlas-stationary30-avHg8uSb/live-once-85f4e81dbedb4e519fa314b94891c9e0`.
Activation JSONL SHA256:
`9b3ed3b5f734809ca8d6fec1a1bc59af5e5c528c704dcea7c86d1e70617902e0`.
Evidence remains intact; grant archive preserved. The installed supervisor labels
its generic admission method phase 'preflight' even when invoked during monitoring;
grant/start flags, timestamp and systemd journal establish this was after start.

Final recorder inactive/static PID0/restarts0, no grant, no autostart. E-STOP remains
latched, commands zero, production PIDs/restarts unchanged; all450 snapshotted
production scripts/config/maps/launch files match. No movement, production restart,
reseed or EKF/AMCL/Nav2 changes. No new activation approval assumed.

Next smallest action: address actual CPU headroom through a separately scoped,
measured proposal, keeping75% unchanged; do not repeat capture until authorized.
Failure logging is now demonstrated on a real refusal, but reliable stationary
recording and moving localization remain unverified. Wheel-XY-pose candidate stays
offline. Public data would still not provide private EKF/AMCL checkpoint history.
Pushed on agent/sync-developer-20261011; exact commit supplied in handoff.
