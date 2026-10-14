# First live30s capture — preflight only

14 October2026,22:44:55 IST resource observation. Status: **PREFLIGHT PASSED;
AWAITING ACTIVATION APPROVAL**. No grant created, recorder not started, no recording.
This is not RECORDING COMPLETED, LIVE CAPTURE VERIFIED or a localization fix.

Exact five upgraded hashes and five unchanged dependency hashes match approved
manifest from installation3ff924e. Collector static/inactive PID0/restarts0;
autostart absent, grant absent. Nav2/explore inactive/disabled. E-STOP latched and
fresh0.1s, commissioning unarmed, commands zero/fresh0.2s. Production service
PID/restart baseline saved read-only; no production service operations performed.
Historical localization17/LiDAR35/motor1 restart counters are not new test failures.

Single five-interval /proc/stat CPU admission, same methodology as baseline:
68.1583,67.1902,66.5529,69.5205,69.7074%. All below75%; no retry-until-pass.
Dashboard CPU70.2%; RAM72%;59C;394350694400 free bytes (~367.26GiB).
This idle observation does NOT prove headroom under collector load. Prior synthetic
cost is not relabeled as live resource impact. Admission must still be fresh at
approved activation and remain enforced during recording; no CPU waiver applies.

Bounded8s read-only ROS subscriber probe received every required topic. No bags or
message payloads recorded, only counts/receipt ages. Counts: scan65, EKF86,
wheel odom86, corrected IM10A86, TF143, raw encoder updates83, each wheel83,
policy84, cmd_vel39, each steering84, staticTF2, AMCL8, particles8. Continuous
receipt ages <=0.143s; AMCL/particles~0.29s. StaticTF latched receipt~7.98s is normal
for nonperiodic static transforms. Source timestamp and full TF-chain validity,
DDS loss and per-message timing remain capture-validation tasks; counts are not
proof of physical sensor accuracy. Probe exited and collector remained inactive.

Evidence retained on Jetson:
- `/tmp/atlas-stationary30-avHg8uSb/first-live-preflight-1791998095238612416.json`
- `/tmp/atlas-stationary30-avHg8uSb/first-live-topic-preflight.json`

## Capture fields not yet applicable

Duration, actual collector CPU/RAM, bag size/throughput, source/receipt ledger,
SQLite/checksums, application drops, DDS loss, queue/callback delays and capture
SHA256: **not measured because activation has not been authorized**. No capture
file exists for this milestone. No before/after recording service comparison yet.
Further stationary-use safety remains unverified. Follow the prepared procedure
in `ATLAS_STAGE20_30S_UPGRADE_READINESS.md` after separate approval. Measure whole
system /proc/stat intervals before/during/after; summarize average/p95/peak; use
collector evidence for process CPU/peak RSS, queue/backlog/callbacks and bytes.
Preserve unavailable physical-I/O/DDS measurements as unknown, not zero.

Approval requested: one bounded stationary30_v1 capture, original75% CPU/RAM80%/
70C guards intact, E-STOP latched, no movement or production restart, no autostart
or automatic retry. A fresh refusal ends the attempt. Grant must be single-use,
profile/hash/boot bound; leave service inactive and consume/revoke grant afterward.

Moving recording remains separately gated. This stationary profile rejects motion.
Public data cannot recover private historical EKF/AMCL initialization or establish
the minimal fusion candidate's effectiveness. No fusion/map/calibration changes.
Git commit identity is supplied in the handoff; branch agent/sync-developer-20261011.
