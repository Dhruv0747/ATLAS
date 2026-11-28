# Stage 32 startup coverage and bounded integrity candidate

2026-10-21; baseline `892eeb5`; branch `agent/sync-developer-20261011`.
OFFLINE ONLY. No Jetson connection, deployment, restart, camera start or recording
performed in this task. Previous live evidence is historical, not current admission.

## Verified cause and remaining uncertainty

The previous worker initialized its CPU baseline AFTER imports and full manifest
hashing. Thus an observed 78.8889% startup window was outside its guard. This is a
confirmed coverage defect. Later streaming guard rejection at 77.104377% correctly
sent SIGINT and reaped the driver. Six depth/zero RGB frames reached the receiver.
RGB reliability and total startup CPU contention remain unresolved.

Existing 1 Hz trace shows baseline aggregate CPU about 70%; at the failed interval
web PID1992 consumed48 ticks, Pi-camera2644 30, telemetry3293 27, Python2045 25,
and kcompactd0 17 (100 ticks/s, six cores). These persistent workloads leave little
headroom. Driver startup previously measured43.33% of one core, later4.95%; it is
not the whole aggregate load. kcompactd activity supports investigating allocation
pressure, but does not prove manifest reads caused kernel compaction. PID2045's
purpose and per-function cost were not captured. Do not stop these processes.

Confirmed expensive operation in source: full-file `read_bytes()` allocates each
manifest member in one block. New code bounds these allocations. Its causal link
to the combined-mode CPU rejection remains UNPROVEN. Existing traces cannot
establish a specific hot function inside the web, vendor or kernel processes.
No unsupported service optimization or vendor mode change has been made.

## Candidate changes (one production file)

`project_atlas/scripts/atlas_vision3d_runtime.py`:

- Parent captures monotonic CPU baseline before spawning shell/Python. Worker
  includes startup/import work in the first complete measurement window.
- Missing/invalid/future/>2s-old baseline fails closed, before opening hardware.
  Existing loaded old web owner cannot launch the new CLI without this seed.
- First resource/sensor admission occurs before integrity validation. Hashing
  has lease, parent, time-budget and full-window guard checkpoints.
- 128KiB incremental SHA256 reads replace whole-file allocations. Every byte of
  all458 files is verified; no cache or skipped hashes. Duplicate/path escape
  rejection added. Full chunks yield2ms to spread work; small files do not sleep.
- All three initial passing samples remain required. Protected services are
  checked again before driver launch. No averaging across failed windows.
- Streaming/cleanup behavior, six mode argument vectors, Domain77, 75/80/70
  limits, 1s minimum/2s maximum window, freshness and calibration gates unchanged.

The baseline provides retrospective admission across Python startup, not a
separate pre-interpreter kill watchdog. If Python stalls >2s it refuses admission
when it runs; no camera can start first. Blocking file I/O similarly fails at the
next checkpoint; it cannot open camera hardware before verification completes.

## Tests and performance (PC only)

77 focused tests passed: startup coverage12, guard simulator13, cleanup9,
Stage30 safety8, existing IR15, USB6, preview4, UI10. Linux tests ran in WSL;
preview/UI actual JavaScript tests used Node on Windows, no skipped dependencies.
Coverage includes first-window overload, overload/stall during hashing, corrupt
payload, unsafe/duplicate paths, cancellation, stale sensors, missing seed,
single-sample streaming failure, lease expiry and child cleanup.
All six driver argv vectors compare exactly with892eeb5. Byte-level installation
and rollback rehearsal passed in a temporary directory. No hardware pass claimed.

Reproducible benchmark: `project_atlas/tools/vision3d/benchmark_startup_hash.py`.
Synthetic458-file fixture, largest16MiB, warm PC filesystem; three alternating runs:

| Metric | Original | Candidate |
|---|---:|---:|
| Peak traced Python allocation |16,949,778–16,971,711 B|461,797–465,274 B|
| CPU time |0.0301–0.0391 s|0.0439–0.0529 s|
| Wall time |0.0285–0.0372 s|0.3036–0.3131 s|

Allocation falls ~97%. Total CPU time increases: checkpoints/validation/yielding
cost work. This is a bounded-memory/burst-spreading candidate, **not a demonstrated
aggregate CPU reduction**. No Jetson performance prediction or RESOURCE BLOCKED
resolution claim. Next profiling must separate native manifest work, driver/UVC
initialization, receiver setup, persistent background work and kernel compaction.

## Package and deployment plan

Local package: `artifacts/astra_concurrent_20261021/startup-coverage-candidate.tar`.
Contains only runtime and manifest. No installer is executed automatically.

- Package SHA256 `af6194d692d52108413abf83ca724bfd33bd6d72dd14c65524141bb12c8f76f0`
- Runtime SHA256 `8f207dc9c7d06cdccc4ec7c82b3e7c6aae29a86121b39c2271ff4e8922226d63`
- Expected live original `feedd883cbb9335569dcf50d33aaf5f66e3db85352dab54b2b3dba76c9137500`

Approval needed: install this single file AND one monitored `rover-status-web`
restart to load the new parent-side sample capture. Without that restart, leave
the candidate offline; do not use a fallback that removes startup coverage.
No other service restart is required. Do not assume restarting web is harmless:
its previously observed CPU transient must be guarded and allowed to settle.

Before install: fresh E-STOP, manual-only, zero commands, no navigation/commissioning,
recorder/camera OFF, exact live/package hashes, disk/resources, service identities
and backup. Preserve old runtime bytes/mode and verify rollback SHA. Atomically
replace only runtime; restart only the approved web service. Verify loaded source,
hashes, OFF state, unchanged protected services and resources. Any failure: stop,
restore exact backup atomically; restoring loaded web code needs the explicitly
approved rollback web restart. No automatic camera activation.

Live camera verification requires separate approval; ONE bounded session only,
full startup monitoring and no retry. Actual RGB delivery and browser rendering
must be measured; six depth frames are not a combined-view pass.

## Calibration and real 3D priority

The existing Depth-only Uncalibrated Preview and IR640x480 settings are preserved.
Prepared calibration target/capture work is independent of RGB startup. Do not
wait for combined RGB to prepare/measure the target. Existing section28.4–28.5 in
ATLAS_STAGE32_ASTRA_INFRARED_INTEGRATION.md defines A4/25mm design, measured square
size and depth reference distances. Those owner measurements and separately
approved stationary IR/depth captures remain required; no synthetic calibration
or installation is substituted. Calibrated metric PointCloud2 stays gated until
validated. Diagnostic real-depth 3D viewing does not require calibration.
