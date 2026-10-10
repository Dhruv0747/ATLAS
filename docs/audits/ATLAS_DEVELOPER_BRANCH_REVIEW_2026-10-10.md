# Developer branch review — 2026-10-10

Read-only comparison against baseline `cc5862a`. No rover movement, motor
command, service restart, production setting change, or branch merge was made
for this review. The branches below are separate descendants of that baseline,
not one combined release. Review each referenced commit before integrating it.

| Branch | Latest reviewed commit | Verified scope and limit |
| --- | --- | --- |
| `claude/amcl-weak-hypothesis-trace` | `f49a9607fb1319d4f33ee12ae94717471b3f1cf8` | Offline trace, 12 parked windows from six recordings, and operator-confirmed manual relocation cause class for the outbound 16:36 start offset. No localization fix deployed. |
| `claude/mission-scan-fit-gate` | `c20dd29be605607735c0b9fbb5bc09ee6c767725` | Adds a fail-closed LiDAR/map check before three saved-map goal dispatches. Checked on 12 recorded parked windows; no controlled live mission pass. Files deployed on Jetson. |
| `claude/safety-hardening` | `118b37306ad19f8f90ffa7a31b74df21d7aae20e` | Sets encoder navigation validation false and archives two scripts that published directly to `/cmd_vel`. Files deployed on Jetson; no movement test. |

## What advanced

The weak room hypothesis had 15 particles at +351.997 s and none by
+362.854 s, while odometry changed only 0.23 mm and 0.0003 degrees. Its
loss is consistent with repeated no-motion resampling and a shrinking cloud;
the recomputed scans did not prefer the wrong region. The internal pre-resample
weights were not recorded, so the exact live selection probability remains a
modelled estimate. The cause of the wrong majority before stopping remains
unresolved.

The AMCL core parked-diversity experiment recovered the failed return window
in 22/30 seeds using a 0.05 m / 2.5 degree nudge. Across 12 windows, the
same policy worsened held-out fit in two seed comparisons and increased jumps
in some correcting windows, reaching nine jumps in one. The standalone
parked-update gate worsened fit in five windows on all 30 seeds per window.
Neither policy qualifies as a runtime localization repair.

The separate outbound 16:36 recording started about 0.55 m ahead of the
scan-best Dhruv Room pose. The operator confirmed ATLAS was moved by hand on
Oct 9; manual relocation is the established cause class for this start
offset. Exact move times were not recorded. This does not explain the five
post-stop AMCL jumps in the different Hall-to-Dhruv recording.

The mission-start check refused six poor-fitting parked poses and passed six
good-fitting poses in the developer's offline replay. It can refuse a saved-map
goal; it does not correct the pose. The 85% threshold was selected from these
parked windows, not from a full range of changing indoor obstacles or a live
mission. A matching scan is also not surveyed ground truth.

## Live state checked read-only

On Oct 10 the Jetson files matched the developer's recorded SHA-256 prefixes:
mission-control `0da12027`, scan-fit core `d60ceeb2`, encoder selection
`1260c463`. Mission control entered active state at 12:20:05 IST, after the
12:19:24 file installation, so that process includes the scan check.
The accepted map YAML currently names `atlas_latest.pgm`, matching the new
check's fixed `.pgm` path. A future map whose YAML names a different image
would need explicit handling.

The live `/atlas/encoder_health` sample reported `navigation_validated:false`,
`autonomy_ready:false`, four selected encoders and a fresh board link. The
installed mux unit sets `ATLAS_MANUAL_ONLY=0`, contrary to the safety branch's
deployment note claiming it remains `1`. At the observed `READY` encoder
state, the mux rejects NAV2 because `autonomy_ready` is false. The mux source
has a distinct three-encoder `RECOVERY` exception when state is `DEGRADED`;
the blanket claim that the flag always blocks RECOVERY is therefore too broad.
No test of that exception was performed here.

## Review findings before treating this as a release

1. **Reconcile the branches.** Each is on GitHub, but the current baseline,
   the developer branches, and the Jetson's older mission-control base differ.
   A merged source tree and the actually deployed byte set have not passed a
   combined regression or live mission test.
2. **Check scan time at its source.** The new mission gate records receipt
   time in its callback. It does not yet compare the `LaserScan.header.stamp`
   with the pose/TF time, so delayed transport could appear fresh. Its TF
   lookup uses the latest transform, not the scan timestamp. Resolve this
   before relying on the check as a complete synchronization guard.
3. **Keep the encoder fail-closed claim precise.** The current health message
   blocks NAV2 in the observed state. The installed manual-only setting is
   off, and the recovery exception must be assessed separately.
4. **Finish localization validation.** The parked nudge is not deployable;
   the cause of the original five post-stop jumps and stable moving pose has
   not been proven fixed. Compare candidate changes in full replay and other
   saved drives before changing production localization.

The developer branches are meaningful progress in diagnosis and mission-start
rejection. They do not establish repeatable autonomous room travel. The next
work can use saved recordings; no driving is required for this review.
