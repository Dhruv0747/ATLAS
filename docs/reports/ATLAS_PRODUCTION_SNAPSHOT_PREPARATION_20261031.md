# Exact-live production snapshot integration preparation — 2026-10-31

GO for separately approved installation-only integration, producer OFF; NOT GO
for producer activation or backend restart. No deployment, restart, benchmark,
Astra/inference or control changes performed. Continue from19dda1c.

## Live baseline and important divergence

Read-only evidence: recovery PID2005 active,NRestarts0, environment only
ATLAS_GNSS_ENABLED=0. Live script mode0644 owner/group jetson:jetson.
SHA2565f44cc1fbd7cdc65b8af17abeb9ecd41cec0a8c8f3ee8274fa9b34362633193a.
Two proposed helper destinations currently ABSENT.

Live recovery includes Stage28 base-maintenance integration absent from this
repository's generic recovery file. Never deploy that generic file wholesale.
Candidate derives from exact live bytes, applying only the existing reviewed
snapshot additions from80f7c8a..2625327. Preserves base maintenance acknowledgement,
dispatch locking, restart holds, fault reporting and all unrelated functions.

## Lifecycle and minimum changes

One patched recovery script plus tools/vision3d/existing_safety_snapshot.py and
restart_safety_observer.py (inert strict Safety dependency; its main is NOT run).
Constructor creates producer only if ATLAS_RESTART_SNAPSHOT equals1. No environment
setting, runtime directory, unit change or restart is part of installation-only.
Existing process stays unchanged. Even a subsequent normal start leaves output
OFF unless separately configured. Three existing callbacks export raw policy,
six Twist fields and encoder JSON with original monotonic receipt times. Recovery
summaries/tolerances are not substituted for strict safety. No new ROS node,
participant, timer, subscriber or HTTP dependency.

Producer shutdown is detected by expiry (<=0.75s producer age, <=1s source age,
checked at consumer polling). It does not falsify freshness during callback stalls.
Atomic replacement exposes complete previous/new JSON; missing/malformed/unsafe
observations reject. Write failure stops export; consumer failures latch. Host
callback scheduling and resource cost remain subject to actual integration tests.
Opt-in initialization/import failure could fail recovery startup: dependency/import
and runtime-directory checks must precede any later activation. Not approved here.

## Focused tests

12 tests PASS in0.065s on WSL: exact-baseline SHA, byte-exact reverse patch, unchanged
unrelated method ASTs including Stage28 guards, identical ROS entity creation,
default opt-in/compile, package hashes, atomic visibility, throttling/source expiry,
HTTP-down independence and producer loss, write failure invalidation, fresh/stale/
wrong-boot/unsafe/missing/malformed data. Completed synthetic benchmark NOT rerun.
Existing isolated Jetson result1.04% one core/13.73MiB process peak remains scoped
to synthetic producer+consumer; live recovery overhead not measured.

## Package

Local prepared directory:work/snapshot-production-review-20261031/package.
Builder:project_atlas/tools/vision3d/prepare_production_snapshot.py (offline only).
Reviewed patch and manifest saved under tools/vision3d/production_snapshot_review.
Manifest SHA256:c6b247d318e5b1abbc7d28e2b3dc746b2112692545903d3aa659e2eaa93d2ef5.
Candidate recovery SHA256:da83d138053a424d40fbff4a94532b864140953191260a32cc36042b5d51276a.
Full helper/patch/plan hashes are in manifest. No installation command is issued
without owner approval and fresh live baseline/safety checks.

## Installation-only procedure and exact rollback

1. Fresh safety/resource/service checks with existing75%CPU,80%RAM,<70C guards;
   latched E-STOP, zero commands and fresh stationary encoders. Verify Astra OFF.
2. Reverify live SHA above,0644 jetson ownership, both helpers absent, opt-in absent;
   abort on drift. Capture recovery/web/protected PIDs and restart counters.
3. Copy exact original recovery bytes with metadata to unique private backup;
   verify backup SHA equals baseline. Save absence ledger for helpers and current
   environment/unit configuration. Verify all candidate manifest hashes.
4. Write helper files via same-directory temporary files and atomic rename,0644;
   install recovery candidate last using same technique. No daemon-reload, restart,
   enablement or environment changes. Verify installed hashes and unchanged PIDs.
   Imports are inert; do not invoke recovery or observer main.
5. Confirm opt-in absent, no production snapshot, no camera/inference change and
   safety remains valid. Stop after installation-only evidence report.

Rollback on any installation/hash/postflight failure: verify destinations are either
approved candidate or baseline (stop on concurrent drift); atomically restore the
backup recovery file,0644 jetson:jetson, verify original SHA. Remove helpers only if
absence ledger confirms they were newly installed and their hashes match candidate.
Never delete a concurrently changed file. Preserve backup, ledger and failure logs.
No restart is required because running process was never replaced/restarted. Restore
original bytes before removing dependencies. Do not alter service configuration.
If any unexpected restart occurs, stop and report; do not enable producer or launch
an automatic recovery restart. Future activation needs separate lifecycle approval.

Requested next approval scope: one installation-only integration of these exact
three files, no restarts and output disabled. Backend package remains untouched.
