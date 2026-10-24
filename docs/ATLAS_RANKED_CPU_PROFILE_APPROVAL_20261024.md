# Ranked native CPU diagnostic: prepared, not executed

Owner authorizes preparation and one admin command, CPU report-only for profiling.
Production safeguards unchanged. No camera/movement/restart/installation.

Two diagnostic Python files and manifest staged under
`/home/jetson/project-atlas-migration/ranked-cpu-20261024`, outside production.
No profiler run by assistant. Fresh safety/resource checks occur inside the
owner-run command; preparation is NOT a safety admission pass.

## Difference from previous capture

Earlier selection was restricted to two Nav2 threads and produced15 on-CPU
samples. This version gathers readable process CPU totals by PID/birth/cgroup,
and thread CPU for11 explicitly allowed ATLAS service groups. Five baseline
samples rank actual tick deltas; up to6 stable eligible threads are selected.
No presumption that Nav2 remains the largest load. Process rows are totals and
thread rows are subsets: never sum both. Non-ATLAS workloads are ranked but NOT
stack-profiled. No command-line/environment capture for unrelated processes.

Native perf20seconds,49Hz user cpu-clock,4096-byte DWARF, no inheritance, no BPF,
no build-id cache. Existing hash-verified perf binary only; no package install.
User CPU sampling still excludes kernel call paths; process user+system totals
and schedstat provide attribution context, not a proven kernel root cause.
Theoretical maximum6*49*20=5880 samples; actual count depends on thread CPU time.
Raw stacks may contain private memory fragments; evidence stays private0600.

One-second safety monitoring,5pre/5post samples; root only for owned profiler
and evidence cleanup, checks as jetson with correct user bus. CPU is valid finite
report-only; RAM80%,temperature70C, freshness deadlines,E-STOP/manual-only/zero
commands/recorder OFF/Astra OFF remain enforced by unchanged verified helpers.
Abort on identity/hash/other guard failure, no automatic retry. Stop only the
owned profiler group. Service PID/restart identities and files checked before/
after. Snapshot cache300ms avoids duplicate scans within a health iteration.

The bounded test does add profiling overhead. Compare observer process CPU,
baseline/profile/post totals and sampling deadlines; do not call phase changes
CPU savings. PID churn, unreadable processes and transient tasks limit accounting.

## Tests and verification

7Linux unit tests pass: delta ranking/top6 cap, PID-vs-TID no-double-selection,
identity changes, no-load rejection, service/user/executable allowlist, native
command bounds, helper hash/CPU-exception/Astra-OFF protection.
Windows run had6passes/1import error because pwd is Linux-only; complete suite
then passed on WSL Ubuntu22.04. No test weakens production gates.
Live read-only checks confirmed Dashboard/voice/safety/UI/gate/probe hashes match
the pinned manifest, service cgroup paths match, and disk reports367GB available.
No current resource safety pass claimed from these setup checks.

Wrapper SHA25641ec29fd68745159f29b151c323743df11378247b637c769c5029cee59743376.
Helper SHA2562b0cd1ee5872070ee21c93780445e8296b9f1a2574b84ad3e7375e98bc959e18.
Staged SHA256SUMS is checked by the owner command before executing.

Keep rover parked, emergency stop latched, Astra/recording OFF. Run once, no retry.
Outer timeout60seconds (sudo password entry occurs before timeout begins).
Output and failure reason persist in unique evidence directory and launch log.

Rollback: none for production. No production file/service is modified. Retain
diagnostic files/evidence for analysis. Raw profile is not committed to GitHub.
CPU exception applies only to this run, not future Astra admission or deployments.
