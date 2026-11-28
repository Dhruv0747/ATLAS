# Visual Cloud CPU and ROS timing measurement — 24 Oct 2026, 22:16–22:36 IST (owner-approved Option 1, read-only)

No service was changed, disabled, restarted or reconfigured. ATLAS was parked throughout: E-STOP latched,
manual-only, commissioning disarmed, `/cmd_vel` zero in every sample. Tool: `project_atlas/tools/vision3d/headroom/atlas_vc_monitor.py`
(subscriptions only, nice 10). Raw data on the Jetson: `~/project-atlas-migration/vc_measure_20261024_2212/vc_monitor2_final.jsonl`
(1123 × 1-s rows).

The phases come from the data, not from the clock. The agent's subscriber entries on watched topics went from 1
(`/cmd_vel`) to 8 at **22:27:16** (page opened), and back to 1 at **22:33:29**. The server last answered the page at
22:33:14 (page closed), so the hold after closing was about 15 s.

| Measurement | Idle (22:16:27–22:27:06, 599 s) | Active (22:27:26–22:33:14, 325 s) | Back to idle (22:33:43–22:36:11, 138 s) |
|---|---|---|---|
| Whole-Jetson CPU mean | 67.1% | 68.4% | 67.1% |
| Whole-Jetson CPU peak (p95) | 72.0% (69.7%) | 77.0% (71.1%) | 71.3% (69.9%) |
| Seconds > 75% / runs > 85% | 0 / none | 2 / none | 0 / none |
| Visual Cloud agent (one core) | 1.6% mean, 2.1% max | 11.9% mean, 29.0% max (1 s) | 1.5% mean, 1.9% max |
| Visual Cloud server (one core) | 0.0% | 1.6% mean, 4.4% max | 0.0% |
| Memory: agent / server | 57.5 MB / 16.5 MB | 57.5–57.8 MB / 14.6–18.9 MB | 57.7 MB / 16.3 MB |
| System RAM | 60.8–68.1% | 61.4–63.7% | 63.2–63.8% |
| `/scan` subscribers | 13 | 14 (+ Visual Cloud) | 13 |
| ROS CPU spikes | none | none at activation (peak 72.7% in the activation second) | none at release (peak 70.1%) |
| Sensor timing impact | baseline | none measurable (table below) | none |

Transitions: idle→active (±10 s) mean 67.3%, max 72.7%. The agent took 25.5% for the single second it created
7 subscriptions (`/scan`, `/tf`, `/odom`, `/yahboom/odom`, `/map`, both costmaps), then ran at 10–11%.
Active→idle mean 67.4%, max 70.1%; the agent returned to 1.4% within 1 s of releasing them.

The two active seconds over 75% (22:28:18, 77.0%; 22:31:15, 75.6%): the top processes were the dashboard
(`atlas_status_web.py`, 38–41%), Pi `camera_node` (35–37%), the base driver (28%), and in the 77.0% second **`polkitd`
at 30.8%** (a systemd authorization request from another client). The Visual Cloud agent was at 10.1–10.5% in both, its
normal active level. These seconds are not attributable to Visual Cloud.

## Critical timing (max inter-arrival gap / max age, seconds)

| Topic | Rate | Idle | Active | Back to idle |
|---|---:|---|---|---|
| `/scan` | 7.8 Hz | 0.305 / 0.239 | 0.307 / 0.231 | 0.313 / 0.246 |
| IMU `/yahboom/imu/data_calibrated` | 10.7 Hz | 0.193 / 0.114 | 0.190 / 0.102 | 0.198 / 0.101 |
| Encoders `/atlas/encoder_update` | 10.7 Hz | 0.185 / 0.117 | 0.207 / 0.125 | 0.194 / 0.105 |
| Motor command `/cmd_vel` | 5.0 Hz | 0.330 / 0.247 | 0.329 / 0.243 | 0.334 / 0.255 |
| Control policy | 10.7 Hz | 0.188 / 0.105 | 0.187 / 0.100 | 0.167 / 0.101 |
| Safety status | 4.3 Hz | 0.338 / 0.257 | 0.346 / 0.248 | 0.334 / 0.254 |
| `/tf` | 18.5 Hz | 0.198 / 0.113 | 0.203 / 0.111 | 0.181 / 0.099 |
| Local costmap (Nav2) | 1.8 Hz | 0.694 / 0.598 | 0.697 / 0.597 | 0.678 / 0.605 |

Service CPU (one core) with the page closed vs open: Nav2 localization 51.1 vs 50.5, LiDAR 3.6 vs 3.6, IMU 7.5 vs 7.4,
mux 15.6 vs 15.4, base 28.2 vs 27.8, safety 12.1 vs 11.9, dashboard 45.2 vs 39.8. No increase anywhere.

## ROS participant-join spike (for comparison)

The monitor's own start (a new participant on the production domain) gave 99.1, 96.9, 90.9% for 3 s at 22:16:12. The
top processes were the **existing** nodes waking up for discovery (`camera_node`, several python nodes,
`foxglove_bridge`), not the monitor. The earlier start at 21:28 lasted ~8 s at 93–99%. Visual Cloud's own activation
creates subscriptions inside an already-joined participant and showed no such spike.

## Answers

1. **Unnecessary CPU spikes from Visual Cloud: no.** No second above 85% in any phase; activation and release
   peaked at 72.7% and 70.1%. Both >75% seconds while active were driven by other processes.
2. **Actual cost:** idle 1.6% of one core (~0.3 points of whole-Jetson CPU). Active: agent 11.9% + server 1.6% ≈ 13.5%
   of one core (~2.2 points in theory); measured whole-Jetson +1.3 points (67.1 → 68.4). Memory constant at ~74 MB.
3. **Interference with navigation: none measured while parked.** Nav2 CPU, costmap and `/tf` rates, and every
   sensor and command gap were unchanged. Visual Cloud also activates automatically while driving; that case was not
   measured (ATLAS stays stationary).
4. **Further reduction without losing mission history:** no change with a *measured* benefit is available. Idle cost
   is already ~0.3 points. The only sizeable cost (~2 points) occurs while the page is open or ATLAS is driving, which
   is when it records. A lighter topic set during drive-only activation could help, but its benefit would first have
   to be measured during a supervised drive.
5. **Is the current on-demand design the best approach: yes, by the evidence.** It switches subscriptions inside one
   long-lived participant: release in ~15 s after closing, return to 1.4% within 1 s, no spike. Starting and stopping
   the service per page visit would save ~0.3 points while closed, and pay a participant-join spike (measured 3–8 s at
   91–99%) on every open.

**Recommendation:** no Visual Cloud change. The measurable sources of 100% spikes are new ROS participants joining
(including `ros2` CLI checks) and other system activity (e.g. `polkitd`). Those, not Visual Cloud, are the next targets.
