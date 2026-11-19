# Stage 32 cleanup deployment and one combined verification

Branch: `agent/sync-developer-20261011`. Approved candidate:
`abc6837181e0273f174753b6fdd181123f5e22e1`.

## Result

Single-file diagnostic cleanup DEPLOYED, hash VERIFIED. ONE concurrent session
was requested through the existing Dashboard API. CPU guard stopped it; no retry.
The Dashboard receiver counted **6 depth frames and 0 RGB frames**. Browser pixel
rendering was not verified. Combined live viewing is **NOT VERIFIED** and resource
blocking is **NOT FIXED**. No invalid-context error occurred in this attempt; that
does not prove the vendor startup race is fixed. Parameter-undeclaration shutdown
errors remain in the retained log. No images or bags were saved.

Only `project_atlas/scripts/atlas_vision3d_runtime.py` was installed:

- Before: `fc807489b06699d73efdd246913849a3d11315d6bfcba707eedd0e1381c9b5aa`
- After: `feedd883cbb9335569dcf50d33aaf5f66e3db85352dab54b2b3dba76c9137500`
- Backup/evidence: `/home/jetson/project-atlas-migration/astra-20261021/cleanup-20261021T210340/`
- Backup file: `atlas_vision3d_runtime.py`; its original SHA was verified before replacement.
- Free storage at installation: 394,357,215,232 bytes.

No service restart, USB permission change, calibration, cloud activation, movement
or safety-policy change. Domain 77 and all stream arguments are unchanged.

## Actual timing and resources

Jetson CLOCK_MONOTONIC seconds (not UTC):

| Event | Timestamp |
|---|---:|
| Worker began | 1959.144313720 |
| Driver spawned | 1962.883254143 |
| CPU guard failure | 1964.701134973 |
| Shutdown handling | 1964.701151806 |
| SIGINT sent | 1964.701208927 |
| Child reaped, return code 0 | 1966.282722662 |

Reap timestamp is observation of process completion, not the exact kernel exit
instant. Publisher creation has **no exact monotonic instrumentation** in the
approved candidate; it remains unavailable. Do not infer it from first reception.

Driver launch elapsed 3.739009 s. Guard failed at elapsed 5.556772 s:
**77.104377% CPU**, 1.010 s window. Signal followed guard failure by 0.074 ms.
Last admitted resource sample: CPU 74.074074%, RAM 68.058633%, max 61.25 C.
CPU failure deliberately short-circuits other measurements: RAM/temperature at
the exact failed sample are not claimed. Driver RSS 94,940 KiB at rejection;
driver CPU 4.953% of one core in that interval, versus 43.331% in its preceding
sample. Worker RSS 19,992 KiB, CPU 0.991% of one core at rejection.

Install admission CPU 69.02/71.65/73.49%, RAM 67.26–67.33%, max 61.125 C.
Final separate stationary check CPU 74.523397%, RAM 67.506563%, max 61.562 C.
There is very little baseline CPU headroom even with Astra stopped.

## New contention evidence and limitations

Persistent 1 Hz scalar process monitoring began before Start. Baseline was
70.17–70.38% aggregate CPU. During the failed streaming interval it measured
77.073%, consistent with the independent guardian's 77.104% on a different window.
At that interval web PID 1992 used 48 ticks, Pi-camera PID 2644 30 ticks,
telemetry PID 3293 27 ticks, and kernel kcompactd0 17 ticks. CLK_TCK=100,
six CPUs; process percentages are one-core, aggregate percentages are six-core.
These are contributors, not proof that any existing service is defective.
The process sampler misses the first interval of newly appearing processes.

**Additional gap discovered:** the independent observer measured 78.8889% during
worker initialization, before the worker's three admission samples began. The
observer was evidence-only, not an abort controller; the worker proceeded through
its own passing admission windows. Therefore this attempt cannot be described as
continuous resource compliance from process creation. The active worker guard
did stop immediately on its own later failed sample. No threshold was relaxed.
This coverage gap must be addressed before another test, not hidden by averaging.

USB/OpenNI connected successfully; UVC opened and negotiated 320x240@15 MJPEG.
The log says `attempt to claim already-claimed interface 1` and then `device
started`. It had only ~317 ms before SIGINT after that log. Zero RGB frames is not
enough evidence to blame permissions, wiring, or declare a separate UVC failure.

## Separately reviewed optimization proposal — NOT installed

1. Extend the existing full-window resource guard over worker initialization and
   manifest validation, with a cancellation path before camera spawn. Preserve
   the 75/80/70 limits, 1-second minimum and 2-second maximum sampling interval.
2. Replace bulk whole-file manifest reads with bounded incremental hashing and
   cooperative checkpoints. Revalidate every byte of all 458 files; no unsafe
   hash cache, no omitted files. This targets a confirmed startup workload, but
   its CPU benefit is **unmeasured**, not a claimed fix.
3. Benchmark that candidate offline on the same package; compare hash equality,
   peak memory, CPU and wall time. Inject corrupt files, cancellation during
   hashing and resource failure before spawn. Never launch on a partial manifest.
4. Retain the production services. Do not disable the Pi camera/telemetry or lower
   image modes to obtain a pass. Process samples show baseline contention but do
   not yet identify a safe service-level optimization.

This is a reviewable design, not a completed performance patch. Native hardware
benefit and RGB delivery require a separately approved single live test after the
startup coverage gap and offline optimization tests pass. No new Start is approved.

## Postflight and rollback

E-STOP latched, manual-only true, commissioning false, source STOPPED, zero
commands; recorder inactive. No Astra process remains. Fresh sensor admission
passed. Protected active PIDs and restart counts were identical:
camera1824, telemetry3293, mux1814, EKF2868, localization4595, LiDAR1815;
web1992. All restart counts zero. No Depth-only or IR retest was performed;
their configurations remain unchanged, not newly hardware-qualified.

Cleanup remains installed: its lifecycle/owned-child cleanup worked and no
service regression was observed. CPU blocking is not a cleanup performance claim.
Rollback: with viewer OFF and fresh stationary admission, verify backup SHA above,
copy backup to a sibling temporary runtime file, atomically replace the runtime,
verify original SHA and protected identities. No restart needed for future workers.

## Evidence and validation

Full scalar evidence: `verification.json` in the backup directory; installation
checks: `installation.json`. PC copy under `artifacts/astra_concurrent_20261021/`.
Driver log copied to PC as `verification-driver.log`; preserve it before any new
session overwrites the live ephemeral log. No raw evidence committed to GitHub.

- verification.json SHA256 `987a4767ee881be559cccc363f34c36c104398a107a6530373bfacdb555e0122`
- verification-driver.log SHA256 `551a7712fc6b4cf66a12b986b9159df21476219994a63ffeebbfc32d4ec5a1d1`
The existing 66 focused regression passes from abc6837 were reused, not rerun.
This deployment adds live hash, backup, fresh admission, shutdown, receiver count
and unchanged-service evidence. It does not prove combined viewing, RGB health,
browser rendering or autonomous navigation.
