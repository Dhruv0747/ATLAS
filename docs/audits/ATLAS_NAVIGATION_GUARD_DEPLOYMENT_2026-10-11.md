# Approved navigation guard validation — 11 October 2026

## Scope and evidence

No physical movement commanded. ROS domain 173, localhost-only fixtures were
isolated from production. Synthetic geometry tests use the installed Humble
Nav2 1.1.20 controller server, FollowPath actions, LaserScan callbacks, obstacle
marking/clearing, inflation and static TF. They do not simulate wheel dynamics,
the full behavior tree, moving localization, or loaded stopping distance.

The native RPP probe passed 11 checks including live dynamic parameter changes.
At the same inflated cost the output was 0.132674 m/s with conversion factor 3
and 0.110000 m/s with factor 15. Existing inflation radius/footprint are unchanged.

The original controller-only action replay commanded motion with scans absent,
five-second-old acquisition stamps, and an unobserved rear sector. A separate
expected_update_rate=0.5 experiment stopped publishing after scan loss but still
accepted old-stamp arriving scans. Silence is not proof of a zero motor command.

## Approved correction

Recovery rejects unknown sectors and stale acquisition/receipt times, including
before its first pulse. The additional mux guard can only veto NAV2/recovery:
0.75 s acquisition/receipt/progress bound, expected sensor frame/mount yaw,
five-degree observation bins. Straight motion requires the corresponding
front/rear sector; arcs require all bins because both steering axles sweep.
Invalid/absent returns are never promoted to free space. One finite ray/bin
is availability evidence, NOT continuous swept-volume clearance. Costmaps and
existing obstacle/ultrasonic guards remain active. Manual sources are unchanged.

The branch contains unrelated AMCL helper changes not installed on the Jetson.
`prepare_live_lidar_guard.py` builds only the approved guard patch on the exact
live mux snapshot. No unrelated AMCL code is included in that installation.

## Results

`action_mux_trial_08`: 15/15 checks passed on that exact live-based candidate.

| Case | Observed result |
|---|---|
| Clear straight, left/right arcs | Nonzero commands preserved |
| 0.51 m front-right point, straight | Straight command preserved in tested horizon |
| Left/right swept corner, occupied rear | FollowPath ABORTED, four raw controller zeros; final mux already zero |
| Unknown rear | 20/20 final commands zero |
| Missing scans after timeout | 20/20 final commands zero |
| Five-second-old scans arriving normally | 20/20 final commands zero |
| New obstacle | Four initial commands then zero/abort; not instantaneous stopping |
| Obstacle cleared | Commands resume for new isolated action |
| Manual command without scans | 19/19 preserved |
| E-STOP | Three observed zeros, no nonzero |

Blocked goals can leave an already-zero mux silent. Acceptance requires an
observed pre-goal zero, fresh controller zeros and an aborted action—not merely
no messages. Four acceptance tests prevent false passes. Earlier failed fixture
runs lacked simulated ultrasonic health or sampled after stop suppression;
their evidence is retained, not counted as deployment passes.

Offline regressions: 12 guard + 13 recovery + 6 existing stop-hold + 4 acceptance
+ 3 inflation = 38 passing tests. Inflation tests ran on Jetson Python because
Windows Python lacks PyYAML. Native probe: 11/11; full integration: 15/15.

Integration process totals: controller 0.59 CPU-seconds / peak RSS 34,596 KiB;
mux 4.71 CPU-seconds / peak RSS 61,580 KiB. These are isolated test process
measurements, not production CPU percentage or additive overhead estimates.
Native probe: 1.382 s wall, 0.128 CPU-seconds, peak RSS 29,964 KiB.

## Stage A deployment

Guard source: `95add0cfecd105f491fb52332558752f5186e294`;
recovery freshness: `14234fe87ba86bc0b3c1b4a883dcf98f03c5213c`.
Installed three-file package and restarted only mux/recovery. All live file
hashes match rehearsal. Direct ROS restart verification observed 138 zero
commands and 299 latched policies, no unsafe observations; final scan/IMU/odom
receipt ages 0.081/0.002/0.075 s. No physical command or goal was sent.

Two earlier attempts were rolled back: first two-second startup check was too
short for node initialization; second dashboard HTTP request timed out. Another
preflight refused a cached non-inactive service report, while direct systemd
showed both navigation units inactive with no activation journal entry. The
finite `verify_parked_guard_restart.py` now observes direct ROS stop/command
traffic and systemd, not dashboard cache. It publishes nothing, cannot release
E-STOP and rolls back on unsafe/missing post-restart evidence. Evidence retained.

Installed SHA256:

| File | Hash |
|---|---|
| scripts/atlas_tight_space_recovery.py | `fadbe8114f77cc3946cbbcae5dd8b6faf1a758aea2c8c53210ac70934688e316` |
| scripts/atlas_cmd_vel_mux.py | `0d95928632f1cac7e8d41f5dfe499eb837cdb014cbf47ac7bebcde6f52ff7dc3` |
| scripts/atlas_lidar_availability.py | `4b3cea2e92b5d2e5dab1b4f23e07ef925ea574acd187f6d3d91b407495c97b8c` |

Stage A rollback (keep parked, latch E-STOP first):

```bash
bash /home/jetson/project_atlas/data/backups/2026-10-11-180447-354595945-stage11b-lidar-guard/ROLLBACK.sh
systemctl --user restart atlas-cmd-vel-mux.service atlas-tight-recovery.service
```

Rollback rehearsal restored exact original bytes. Removing the newly added
helper during rollback is scoped to that one file; backups remain intact.

## Real-scan limitation discovered after deployment

A ten-second, read-only dry evaluation of the installed guard received 68 scans.
All 68 vetoed hypothetical navigation in each direction; no commands published.
The last scan was fresh (0.143 s) in `laser_frame`, but only 61/72 bins had finite
valid observations: four missing forward bins, six rear, eleven overall. This
is a conservative availability veto, not evidence of an occupied sector or a
sensor hardware fault. It is also NOT an autonomous usability pass. Validating
an observation policy appropriate to the actual swept path remains necessary;
do not simply weaken coverage or turn invalid ranges into free space. Manual
remote driving is deliberately outside this new veto.

## Stage B deployment

Installed from `6b0f462abcff5d1c59bbf90f1585a2c13939acf5` in both live copies:
`/home/jetson/project_atlas/config/nav2_params.yaml` and
`/home/jetson/project_atlas_ws/src/tortoisebot_bringup/config/nav2_params.yaml`.
The second is the actual localization launch input. Both SHA256:
`2411371c89751eba9f817b3e6728ab08fa3e8820f6727c08713298c18ee08631`.
This preserves two live CRLF lines; LF-normalized SHA matches the source blob.
Runtime controller factor changed successfully 3.0 -> 15.0 and was read back;
local costmap factor remains 15.0. No service restart for B. Final direct check:
82 zero commands, 174 latched policies, scan/IMU/odom ages 0.130/0.075/0.051 s.

Stage B rollback (parked and latched first; no localization restart needed):

```bash
bash /home/jetson/project_atlas/data/backups/2026-10-11-180717-342176253-stage12-inflation-contract/ROLLBACK.sh
bash /home/jetson/project_atlas_ws/src/tortoisebot_bringup/data/backups/2026-10-11-180829-571179806-stage12-inflation-contract/ROLLBACK.sh
source /opt/ros/humble/setup.bash
ros2 param set /controller_server FollowPath.inflation_cost_scaling_factor 3.0
ros2 param get /controller_server FollowPath.inflation_cost_scaling_factor
```

Both config-copy rollback rehearsals restored original bytes. All five installed
file hashes were rechecked after installation. Scratch evidence retained under
`/home/jetson/atlas_recorder_smoke_KWJkzy/`; no existing diagnostics deleted.

## Live resource and service observations

Ten dashboard resource samples per window (two-second spacing): CPU mean
70.82% before, 79.05% after; RAM mean 5,363.9 MB before, 5,948.2 MB after.
Final temperature 60 C versus 59 C before. The after window overlaps final
verification processes; these are whole-Jetson workload snapshots, not an
isolated measurement of guard overhead. No claim of unchanged overhead or
maximum-load qualification is supported. Ten final HTTP resource requests
completed without error; earlier startup checks experienced a timeout.

Mux PID 330413 and recovery PID 330414 active, NRestarts=0 after deployment.
Localization PID 5670/NRestarts=2, motor telemetry PID 1878, remote PID 1930,
LiDAR PID 5442/NRestarts=5 are unchanged from baseline (restart counts predate
this rollout). atlas-nav2 and atlas-explore remain inactive. Localization's
existing Nav2 components were not stopped/restarted. Stop latched, final command
zero, commissioning unarmed. Encoder telemetry is live but autonomy_ready=false
and navigation_validated=false; this rollout does not bypass that qualification.

Final independent remote check: 338 Joy messages over two ten-second windows,
last age 0.097 s; 95 zero commands and 202 latched policies. The dashboard's
"joystick unavailable" stop reason was retained from startup: RemoteStop keeps
the original latch reason even when neutral joystick packets resume. It is not
evidence of current link loss. No reset/unlatch command was issued. Physical
manual response after rollout remains for the operator test.

## One supervised manual test (not yet performed)

Only after remote input is confirmed live, charger disconnected and front/rear
and turning clearance checked: use the existing remote release procedure, drive
about 20 cm slowly, make gentle left/right steering inputs where clear, stop,
and press B. Check steering response, LiDAR freshness, and prompt zero command
on the dashboard. Use the existing opt-in recorder for that session when the
operator is ready; no new continuous service is enabled. Do not select an
autonomous goal or recovery. A successful manual test does not validate Nav2
obstacle avoidance, moving localization or autonomous return-home.

## Remaining acceptance

Supervised manual operation and a later separately authorized autonomous test
remain necessary. These tests do not resolve historical AMCL jumps, certify
moving localization, qualify scan timeout under maximum load, or establish
physical braking distance. Availability guard may conservatively stop turns
when some sectors have no finite return. Do not bypass it to force progress.
