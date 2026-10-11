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

## Deployment

Pending staged installation and live verification. No autonomous acceptance is
claimed. Keep E-STOP latched and autonomy disabled. Preserve maps, recordings,
steering calibration and AMCL process. Update both installed config copies and
the one dynamic controller factor without restarting localization.

## Remaining acceptance

Supervised manual operation and a later separately authorized autonomous test
remain necessary. These tests do not resolve historical AMCL jumps, certify
moving localization, qualify scan timeout under maximum load, or establish
physical braking distance. Availability guard may conservatively stop turns
when some sectors have no finite return. Do not bypass it to force progress.
