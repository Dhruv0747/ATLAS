# Background-search CPU pacing — 15 October 2026

## Scope and confirmed evidence

Continues the parked manual-only CPU checkpoint; no earlier localization replay
was repeated. A 45-second all-process sample found three system CPU intervals
above 75% (mean 70.846%, peak 78.387%). At the two highest intervals the
suggest-only localization monitor used 74.27% and 72.68% of one core. This
identifies a contributor, not the sole cause of all system excursions.

Only the monitor's background global-search worker is cooperatively paced to
10% of one thread's CPU time (after a measured 20% intermediate trial). This
is not a hard process/system CPU ceiling and
does not affect its ROS callback thread. No search candidate, scoring rule,
threshold, input, geometry, recheck interval or 30-second wall deadline changes.
The calling worker sleeps in at most 50 ms pieces, checking the deadline during
waits. Other services and sensor publication rates are untouched.

## Validation

56 focused offline tests pass: six pacing tests, four deployment-readiness tests,
28 monitor/state-machine tests, 17 core/evidence/status tests and one equivalence
test covering three distinct/ambiguous-room scenarios. Exact hypotheses/order,
fits and verdicts match unpaced search. Syntax checks pass. These fixtures are
not a physical navigation test or proof that localization is fixed.

The first PC run needed UTF-8 mode for existing source-reading tests. The broad
legacy verification suite was also attempted: five old seeder-contract tests
fail and two people-experiment imports require unavailable `rosbags`. Neither
seeder nor those experiment files were changed; do not call the broad suite
green. Targeted core and monitor regressions above are green.

## Deployment and safeguards

Original monitor/core hashes matched reviewed Git HEAD. First installation's
dashboard postflight timed out: it automatically restored the original monitor.
Failure evidence remains in backup `20261015_search_pacer_18c27b52`.
After correcting the verifier's bounded read-only readiness observation, a
second supervised installation verified successfully. Unsafe values fail
immediately; only transient HTTP failures/stale arrival can settle. No limit
was raised and no recording was activated.

Intermediate verified backup: `/home/jetson/project_atlas/data/backups/20261015_search_pacer_f113eafa`.
Monitor SHA256: `cddbbc8d44a07b57c62a6ec4160cbbe9c0b02e4fe82d91ab126bafd66f68839b`.
20% pacer SHA256: `3f8331d781b9776214221b97f9bb78376f161734680f73f24bc0c3d436c7ec16`.
Final 10% pacer SHA256: `584822ad28f4b283ba9a27d129110d529af239241ebc351c3da112dd7a6df3db`.
Final backup: `/home/jetson/project_atlas/data/backups/20261015_search_pacer_6dceb15e`.
Only diagnostic monitor restarted (final PID 48253); base, EKF, AMCL, LiDAR, IMU,
camera and mux identities/restart counts and protected hashes remained unchanged.
Its original 60% cgroup quota remains unchanged.

Startup showed dashboard CPU 89.9%; this is explicitly not a recording pass.
Transient monitor TF discovery failure recovered through its existing schedule.
Two subsequent searches completed in 6.77 and 6.61 seconds. The first successful
result's existing `search_s=37.17` includes a prior failed check and the 30-second
recheck wait: monitor timing code retains the episode's first start until its
first successful result. It is not a measured 37-second paced-search duration.
That separate diagnostic timing issue is documented, not silently altered here.

## Intermediate measurements and final validation

At 20%, 90 consecutive one-second samples: mean CPU 70.612%, peak
79.798%, two intervals above 75%; RAM 70.60%, maximum thermal reading 60.937 C,
free storage 395506204672 bytes. System mean/peak do NOT establish an improvement.
A follow-up matched 45-second process sample measured monitor peak 32.19% of one
core (versus 74.27% before), with system peak 75.229% and two intervals above75.
This confirms smoothing of that worker, not a total system fix. The single next
change reduced its budget from20% to10%; equivalence/pacing tests passed again.
Live search at10% completed in14.22 seconds, still inside the unchanged30-second
deadline. Startup dashboard CPU89.2% was preserved as a transient failure of
recording headroom, not hidden in the steady-state mean.

At10:15:48 IST the final short safety/resource check passed: CPU maximum73.038%,
RAM67.657%, maximum temperature60.781C. This alone is not sustained validation.
The safeguard is unchanged at CPU75%, RAM80%, temperature70C. Recording stays
OFF; localization remains LOST/DEGRADED and navigation unauthorized. Network
banner timeouts prevented one LAN measurement from starting; Tailscale remained
usable. No network settings changed and failed attempts were not counted as data.

Final90-second process-correlated measurement at10%: system mean70.747%,
peak78.696%, three intervals above75%. Monitor peak23.24% of one core, versus
74.27% before (about69% lower burst). Search14.23s; original deadline and result
discard on changed/stale input remain active. One result was discarded after
the monitor's motion/staleness episode changed; zero commands were still
observed. This does not establish physical motion or explain that input event.

The largest remaining system peak coincided with `polkitd`32.29% of one core,
while monitor used13.30%. This is a new attribution lead, not proof of which
requester caused it. A15-second headers-only system-bus profile was denied
`BecomeMonitor` access; fallback eavesdropping yielded no authorization calls.
No meaningful requester attribution is available without an authorized privileged
trace. Do not disable polkit, change networking/failover, weaken authorization,
lower safeguards or throttle essential/control services to force a pass.
The next necessary investigation is a bounded privileged authorization-request
trace correlated with CPU, before changing the requesting application. No such
privileged trace or service change was performed in this task.

Verdict: the identified diagnostic-search burst is materially reduced; total
CPU headroom is still UNRESOLVED. No recorder admission or autonomy pass claimed.
Final10:18:48 IST preflight is BLOCKED on CPU77.814%; RAM68.002% and all required
thermal readings (maximum60.750C) pass. Stop/manual-only/zero-command and recorder
OFF remain verified. The earlier short pass is not the final admission result.
Final10% deployment/measurements are in `20261015_search_pacer_6dceb15e` including
`final90.json`; the original and both trial ledgers remain preserved.

Raw evidence is preserved locally under `artifacts/cpu_manual_only_20261015/`
and the intermediate Jetson backup's `resource90.json`; generated logs are not in Git.
Rollback to the pre-pacing monitor: restore `monitor.original` from the first
backup (`20261015_search_pacer_18c27b52`) to
`/home/jetson/project_atlas/scripts/atlas_localization_monitor.py`, then restart
only `atlas-localization-monitor.service` while stopped. The inert helper may
remain for evidence. Never restart control services or release E-STOP as part
of this rollback.
