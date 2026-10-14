# ATLAS core localization resumption — 14 October 2026

Branch: `agent/sync-developer-20261011`. This is a read-only analysis of the
Stage 16 verdict history on the Jetson and existing October 9 rosbag2 SQLite
recordings. ATLAS was not driven, reseeded, rebooted, recalibrated or redeployed.
The accepted map and safety settings were not changed.

## New startup evidence (P0)

The Stage 16 `localization_verdict_history.jsonl` exists and contains four
verdicts, including three attempted searches for each failure. All four use
the same accepted map YAML SHA-256
`d957f0fe3b8b48166751ef0226ba5f7abdd5454e6f44fac4c9e7b430f00c45e4`
and the same saved LiDAR-to-base transform `(-0.05 m, 0, 180°)`.

| Verdict time IST | Boot ID prefix | Startup decision | Best fit / margin | Best candidate (m, degrees) | Scan evidence | AMCL seed |
| --- | --- | --- | --- | --- | --- | --- |
| 11 Oct 20:59 | `1de1f248` | UNKNOWN, three attempts | 0.923/0.054, 0.912/0.057, 0.907/0.054 | (3.335, 1.085, 134) | 22–24 scans; 309–313 valid rays; ≥73 in each quadrant | None recorded |
| 11 Oct 21:08 | `ac19b91a` | VERIFIED | 1.000/0.126 | (0.235, −1.535, 74) | 22 scans; 305 rays; ≥65/quadrant | Yes, via service |
| 13 Oct 21:23 | `0152ce28` | UNKNOWN, three attempts | 0.945/0.032, 0.946/0.014, 0.950/0.028 | (0.035, −2.635, 78) | 21–22 scans; 262–266 rays; ≥58/quadrant | None recorded |
| 14 Oct 10:47 | `188e5288` | VERIFIED | 1.000/0.129 | (0.175, −1.735, 73) | 23 scans; 294 rays; ≥62/quadrant | Yes, via service |

The first failure missed the **absolute fit** gate of 0.93, by 0.007 on its
best attempt. The second exceeded that gate but failed the **uniqueness** gate:
another map location scored within 0.014–0.032. The verifier correctly
withheld an initial pose in both cases. This explains the software decisions,
not the physical reason each alternate-position scan fits poorly or ambiguously.
The two failed scan sets differ substantially (median 313 mm absolute
per-angle range difference where both have returns). The actual alternate
position, heading and nearby objects were not measured in the saved evidence;
therefore one cannot assume identical scan geometry across the two attempts.

The history is **failure → Home success → failure → Home success**, rather than
three consecutive verdicts. The 13 Oct verdict has the same Jetson boot ID as
the 11 Oct 21:11 boot, so it records a restarted localization check or service,
not a new Jetson boot. That does not dispute the operator's power action on
other rover components. The last Home success came from the **startup verifier**:
`seeded=true`, `seeded_via=service`. A Dashboard marker alone was not used as
proof, and the history does not establish whether CHECK MY LOCATION also ran.

Stage 16 captured the per-attempt median scan ranges, source scan stamps,
valid-ray coverage, top five global candidates, map hash and LiDAR transform.
No `capture_error` appears. The first short boot's journal is no longer in
`journalctl --list-boots`, so its LiDAR startup retries, exact first raw scan,
scan-time TF history and AMCL publication cannot be reconstructed from journal.
The saved verdict records a successful fixed LiDAR transform lookup and enough
scans for every attempt. The per-boot file does not archive raw individual
scans, complete dynamic TF, AMCL particles or AMCL publication after seeding.
Thus occlusion, map geometry error and changed heading remain hypotheses for
the low fit; source/coverage evidence does not support a simple missing-sector
or no-TF diagnosis.

## Moving localization and heading (P1/P3)

The existing October 9 synchronized audits already place the first observed
heading divergence **before** the AMCL jumps. In the 185.23–189.58 s turn of
the Hall-to-Dhruv recording, wheel-derived yaw was **+7.42°**, IM10A gyro
**−18.96°**, and LiDAR ICP **−16.09°**. At the end of the 10 Oct fast manual
drive, saved endpoints implied about **−97.5°** true turn, while EKF gave
**−44.9°** and wheel odometry **+15.4°**. That latter drive has no bag during
motion, so the exact first failing sample cannot be recovered. October 9
recordings show post-stop AMCL jumps, including five >0.5 m and a 2.206 m
maximum, after a previously dispersed/multimodal particle cloud. Scan and
TF publication did not have a matching gap in the documented event window.

The prior cross-bag and motion audits already measured the EKF's configured
0.2 s future TF offset and a suspected 0.10–0.18 s timing contribution; they
did not establish a production-safe timing correction. Wheel heading uses
**commanded** steering, not physical steering-angle feedback. The evidence
supports a motion-estimation/particle-tracking failure chain but does not
prove which physical effect caused the wrong wheel yaw or the isolated fast
IM10A under-turn. No EKF/IMU/AMCL tuning is justified by the new startup data.

## Encoder receipt timing (P2, new offline measurement)

`project_atlas/tools/diagnostics/encoder_packet_timing.py` reads the original
SQLite bags without ROS or motor access. It decodes headerless Int32 encoder
topics and the existing `/atlas/encoder_update` diagnostics, distinguishing
bag receipt interval, driver-reported packet age, update sequence and count
changes. These are different clocks; the Int32 messages contain no MCU
sampling timestamp.

| October 9 bag | Per-wheel receipt median / p95 | Long receipt gaps | Diagnostic packet age | Diagnostic sequence |
| --- | --- | --- | --- | --- |
| Hall→Dhruv 12:22 | ≈100 / 111 ms | M1/M2/M4 one >350 ms each, M3 zero; maximum 473 ms | 21.1 ms median, 41.1 ms p95, 66.9 ms max | 0 gaps in 2,919 updates |
| Outbound retry2 | ≈100 / 112 ms | none >350 ms | diagnostic topic absent | unavailable |
| Return retry2 | ≈100 / 113 ms | two >350 ms per wheel; maximum 568 ms | diagnostic topic absent | unavailable |

In the Hall→Dhruv bag the diagnostic stream marked **zero stale packets**;
65 updates were nevertheless `feedback_unavailable`, which is a different
estimator state. Counts changed on 484 M1, 430 M2, 379 M3 and 428 M4
intervals; repeated values over the entire bag include parked time and cannot
be called lost counts. The recorded stream does not show sustained grouped
arrivals or missing published sequences. It also cannot rule out batching or
missed counts inside the MCU before USB transmission. At 0.10–0.45 m/s the
separate ICP audit found M1/M4 at 0.64–0.72× and M2 at 0.51–0.64× LiDAR
distance; M3 contributed little in those selected segments. This is a metric
accuracy problem even when packets arrive regularly. No arbitrary CPR change
or permanent M3 exclusion follows from this audit. In the separate 16:36 bag,
M1/M3/M4 counts never changed while M2 changed on 218 intervals. That session
had no accepted motion pairs in the previous scale audit and cannot qualify
the three flat channels as faulty without an independent motion reference.
At the evidence level M1/M2/M4 are **fresh but metrically degraded** in the
main moving bags; M3 is **fresh with inconsistent motion contribution**; no
channel is proven stale in the main Hall→Dhruv bag. The existing production
three-channel policy was not modified.

## Map and navigation context (P4)

The accepted map is unchanged. The prior seven-traversal map audit found
272 wall cells contradicted by at least three drives and an alias near
(3.9–4.1, −0.7). The mapping return leg added parallel walls about
0.05–0.6 m from earlier walls. Candidate v1 was rejected and v3 gave no
measured benefit. The new alternate-position scan history is consistent with
map ambiguity but does not locate a particular erroneous cell. There is not
enough measured placement or fresh corridor evidence to promote a new map.
There is a verified **source versus deployed map difference**: the 11 Oct PC
backup of the Jetson's accepted map hashes to YAML `d957f0fe…` and PGM
`4beb26d5…`, matching the four startup verdicts. The repository's
`project_atlas/maps/atlas_latest.*` instead hashes to YAML `d483d018…` and
PGM `7b8a4090…`; its YAML origin is (−2.75, −8.08) versus the accepted
(−3.89, −8.46). A local replay against the repository copies would therefore
test the wrong map. The archived accepted pair must be used for future
comparisons; neither copy was replaced in this work.
The observation-coverage navigation guard remains conservative; no Nav2 or
recovery permission changed in this work.

## Change, tests, deployment and next action

The only code addition is the **offline** encoder packet timing audit and its
focused CDR/timestamp tests (**2/2 passed**). The audit parsed all six locally
available bag directories; the stationary bag has no encoder topics. No live
file, unit or configuration was installed
on the Jetson. The diagnostic runs from the PC and has **zero ongoing Jetson
CPU/RAM cost**. The last documented Jetson handoff measured about 4.9/7.6 GB
RAM and load average 13 on six cores (11 Oct); that is not a current reading.
The Jetson answered SSH for the Stage 16 history and boot list, then timed out
on a later journal request. Current service, safety and dashboard state are
therefore not re-certified by this report. The latest verified live deployment
remains Stage 16 with its existing backup
`~/project_atlas/data/backups/2026-10-11-202350-349365561-stage16-startup-evidence/ROLLBACK.sh`.

The bounded next step is to preserve a measured alternate-position reference
(physical position/heading and nearby movable objects) alongside an **ordinary**
future startup verdict. It can distinguish map geometry from placement or
occlusion without lowering the 0.93/0.06 thresholds. For moving localization,
an opt-in diagnostic recording of one supervised drive is still required to
identify the first divergence; existing bags cannot reconstruct the missing
10 Oct motion. No autonomous navigation claim is made.

References: [cross-bag comparison](docs/audits/ATLAS_LOCALIZATION_CROSS_BAG_2026-10-09.md),
[motion investigation](docs/audits/ATLAS_LOCALIZATION_MOTION_INVESTIGATION_2026-10-10.md),
[map repair](docs/audits/ATLAS_LOCAL_MAP_REPAIR_DHRUV_HALL_2026-10-10.md),
[encoder scale](docs/audits/ATLAS_ENCODER_SCALE_BY_SPEED_2026-10-11.md),
[previous handoff](ATLAS_NEXT_SESSION_HANDOFF.md).
