# One Depth-only verification after direct-worker deployment

2026-10-21; deployed candidate ed450f9, deployment08ad26f. One Dashboard Start,
Depth-only, maximum60s; no retry. Result: RESOURCE BLOCKED, not Preview verified.

## Fresh admission

Runtime SHA256 ebaaa3c7990d982cfd8e65f217baae9a1a15c71a0aa396594cc597e5b04256b9.
CPU69.1379,73.5703,70.2521%; RAM68%; maximum60.812C. E-STOP latched,
manual-only, commissioning disarmed, zero commands/outputs, mission READY,
recorder OFF. Pi Camera/LiDAR/IMU/M1-M4 feeds fresh; both Astra USB identities
and effective access checked by existing extra_safety. No permissions changed.
Browser reloaded before Start because it initially displayed an older UI/session.

An initial read-only monitor mistakenly recognized an old persisted terminal
worker as the current one. It exited without starting a camera; corrected monitor
requires a new startup monotonic baseline. Both evidence files retained. This was
not a camera retry. A shell quoting error also occurred before any admission or
camera action. Neither affected production files.

## Actual single session

|Event|Monotonic seconds|
|---|---:|
|Worker started, PID36627|3540.142897830|
|Driver spawned, PID36715|3543.436359181|
|CPU guard failed|3545.946069154|
|Session stopping|3545.946085731|
|SIGINT sent|3545.946129988|
|Driver reaped, exit0|3546.565509821|

Failing CPU76.0757315%,1.005s window; five previous resource samples retained.
Last passing check CPU71.6724%, RAM67.6698%, max60.875C. RAM/temperature at the
failed CPU sample are not measured because require_cpu rejects before snapshot.
Shutdown took0.6194s from SIGINT. Vendor parameter-undeclare cleanup errors remain;
no invalid-context exception was observed in this session.

Dashboard reported **17 real Depth frames**,160x120,16UC1, largest received gap
0.38s. Post-stop observer captured10.7327fps before freshness expired. Exact
per-frame age during live viewing was not captured; no freshness claim beyond
the guard and recorded arrival evidence. RGB/IR were not requested.

The browser was visible and its normal polling maintained the viewer lease.
The agent observed Running/no frames then RESOURCE BLOCKED. Guard shut down
before the Uncalibrated Preview could be enabled/verified. Therefore point count,
rotate/zoom/pan/selection are **NOT TESTED**, not passes and not zero-point proof.
No screenshot/video/rosbag or image payload recording was saved. Only scalar
diagnostics retained. Calibrated PointCloud2 remained disabled.

Independent1s /proc monitor CPU sequence:
69.4017,69.4974,70.3072,72.3077,69.5876,69.9828,68.8042,66.9535,
70.0173,73.3677,68.2540,70.5986,72.8696,72.9915,74.7856,72.1170.
Different window alignment explains why this observer did not reach the worker's
76.0757%; the worker guard is authoritative and was not weakened.

## Postflight and evidence

Driver absent and safely reaped. Dashboard Stop clicked after automatic shutdown;
retained status remains RESOURCE BLOCKED with driver_stopped=true, not streaming.
E-STOP latched, zero commands, recorder OFF, fresh protected feeds, mission READY.
RAM67.0023%, max60.718C. All protected PIDs/restart counters unchanged:
camera1824,telemetry3293,mux1814,EKF2868,localization4595,LiDAR1815; active,0restarts.
No service restart, navigation, movement, calibration or production file change.

Jetson evidence:
`/home/jetson/project-atlas-migration/astra-20261021/preview-direct-live.json`
SHA256 `4de1c50ab0027cfcd82a54bd2647a1b3d853dec3a455d0786268f6ba2e31fc4d`.
PC copy: artifacts/astra_concurrent_20261021/preview-direct-live.json.
Older monitor-only evidence preview-direct-once.json is NOT the new session.
Raw diagnostic artifacts not committed; this report contains reviewed scalars.

## Conclusion

New progress: first startup admission passed and actual depth frames reached the
Dashboard receiver, unlike the earlier pre-driver rejection. This single run does
not establish Jetson CPU savings or reliable preview. Resource contention remains.
Next work should analyze existing runtime/receiver/background CPU costs offline;
no further Start without separate owner approval. Preserve75/80/70,Domain77 and
the prelaunch guard. Do not declare real3D Preview verified.
