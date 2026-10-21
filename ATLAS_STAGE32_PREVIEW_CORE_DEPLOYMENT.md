# Depth preview core deployment — verified

2026-10-21. Owner-approved candidate e01fc36 installed; only
`scripts/atlas_vision3d_core.py` replaced and only rover-status-web restarted.
No Astra Start, image/ROS recording, USB permission changes or movement.

## Hashes and rollback

Installed SHA256: `49777c0c3a3c2542107dcccba0ef26e234a31ab22729b055ca8bc260bff501a2`
Verified original/backup: `1e4c095d5d2ae76aae528e09aa152f66218d4838855e882f1cb91196a7efe63e`
Backup/evidence directory:
`/home/jetson/project-atlas-migration/astra-20261021/preview-core-20261021T213723/`
Contains original atlas_vision3d_core.py, deployment.json and cpu.jsonl.
Deployment JSON SHA256: `245bde6a0bbf5a47be20b067ac46f44a21e3ac883c6570ad66efc128c0c5718f`
CPU trace SHA256: `a8ce0c4e13cbdcf0222e17d5e5a93a55fa1cb6ae0f4c0fa45c4f9a34977f5af4`
Local copies retained in artifacts/astra_concurrent_20261021/preview-core-*.
Raw artifacts not committed. Reviewed scalar summary below.
Rollback not needed: validate backup hash, restore core atomically, restart only
web under stationary checks, then verify hash/protected identities/freshness.

## Admission and resources

Fresh CPU72.3183,69.2437,69.6370%; RAM68.16–68.17%; max60.781C.
Free disk394277769216bytes. E-STOP latched/manual-only, commissioning disarmed,
source STOPPED, cmd_vel and four outputs zero; mission READY, recorder inactive.
Pi Camera/LiDAR/IMU/M1–M4 messages fresh within2s. Astra driver absent;
both verified Astra USB nodes had effective RW access. All live hashes matched.
Original byte backup verified before atomic install. Candidate compile passed.

Persistent /proc/stat monitoring began before restart. Restart monotonic
3951.770563301. Pre-restart samples69.7232,68.4764%. Restart peak100%.
Final five consecutive samples (monotonic seconds,CPU%):

```text
3985.678645 68.5567
3986.679671 69.4301
3987.680461 72.3368
3988.681243 69.3739
3989.682088 69.4683
```

Settling confirmation ~37.91s after restart, within45s bound. No camera launched
during the transient. Postflight RAM68.1698%, max60.625C. These idle/restart
measurements do not establish live depth-conversion CPU savings.

## Recovery and invariants

Web active PID34740 ->40386, NRestarts0 (manual restart).
Protected service PIDs and restart counts unchanged, all active/NRestarts0:
camera1824,telemetry3293,mux1814,EKF2868,localization4595,LiDAR1815.
Fresh required sensor feeds and four zero motor outputs reverified. E-STOP remains
latched; source STOPPED/manual-only, mission READY. Recorder OFF, Astra summary
OFF/no driver process. Both USB identities/access unchanged.

Runtime, web adapter, geometry, UI JavaScript, live config, stationary gate and
ROS probe hashes preserved. Thus75%CPU/80%RAM/70C,1s guard,Domain77,Depth/IR modes,
calibration restrictions and UI unchanged. Installed core matches94-test candidate.
No new physical performance result claimed.

Next approval: ONE guarded stationary Depth-only Uncalibrated3D Preview test,
fresh checks, stable heartbeat, actual point rendering/interaction verification,
stop on guard failure and no retry. Not authorized by installation approval.
