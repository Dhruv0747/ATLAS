# Stage 28 — supervised DDS discovery-storm rehearsal (PROPOSAL, not run), 2026-10-27

Purpose: find out whether the independent safety observer keeps **fresh** E-STOP, command and telemetry evidence
while the Jetson goes through the same discovery storm that a recovery restart caused in Stage A. A pass is the
precondition for asking for another Stage A attempt.

Nothing is deployed and no service is restarted. The only new process on the rover would be one short-lived test
node (≤ 15 s). **No live run has taken place; it needs separate explicit approval.**

## 1. Test node: `atlas_dds_storm_probe.py`

| Kind | Name(s) | Endpoints |
|---|---|---|
| Subscriptions | `/atlas_storm_probe/sub_00` … `sub_15` (std_msgs/String, private; nobody publishes there) | 16 |
| Publishers | `/atlas_storm_probe/pub_0`, `pub_1` (never publish) | 2 |
| rclpy defaults | `/rosout`, `/parameter_events` publishers | 2 |
| rclpy defaults | 6 parameter services `/atlas_storm_probe/atlas_storm_probe/{describe_parameters, get_parameter_types, get_parameters, list_parameters, set_parameters, set_parameters_atomically}` | 12 |
| Service clients / actions | none | 0 |
| **Total** | one participant | **32** (same as atlas_sensor_recovery) |

- **Defaults:** confirmed against the Jetson's Humble `rclpy/node.py`. `/clock` is subscribed only with `use_sim_time`.
- **No control topics:** no `/cmd_vel`, `/atlas/control_policy`, E-STOP, joystick, motor, steering, Yahboom or RC topic.
  A topic outside `/atlas_storm_probe/` makes the probe refuse to start.
- **Self-check:** the probe verifies its own inventory from the ROS graph and fails if anything differs, including any client.

Fail-safes inside the probe, all armed **before** `import rclpy`:
- `SIGALRM` hard termination at 14 s;
- `PR_SET_PDEATHSIG = SIGKILL`, so it dies with the supervisor;
- it refuses to start without a fresh supervisor heartbeat, and exits within 0.1 s once the heartbeat is > 1.0 s old;
- it holds the node 6 s, then destroys it and exits.

DDS transport is forced to `FASTDDS_BUILTIN_TRANSPORTS=UDPv4`. Fast DDS 2.6.11 on the Jetson honours this:
`rover-base-telemetry` (UDPv4) has 0 `/dev/shm/fastrtps` mappings, while recovery (default transport) has 22. So even a
SIGKILL cannot leak SHM segments.

## 2. Expected CPU impact (model from three measured restarts; to be confirmed by the run)

| Phase (s after spawn) | Expected |
|---|---|
| 0–3 | login shell + `setup.bash` + rclpy import: about +7 points (like recovery: 71–74 %) |
| ≈ 2.5–9 | join storm in the 44 peers. Model: 5.52 core-s per participant + 0.243 × 32 = **≈ 13.3 core-s**, the same as Stage A (12.3–13.3 measured). Expect 95–99.8 % for about 6–7 s, last sample over 75 % near +8.5–9 s |
| ≈ 9 | participant leaves (node destroyed). Leave cost is **unmeasured**; any sample > 75 % after +10 s aborts |
| 9–40 | strict 30 s window, every sample ≤ 75 % |

Before the spawn, the observer subscribes 4 endpoints on the existing bridge (about 1 core-s, spread). All CPU, RAM and
temperature samples taken before the spawn must already meet the strict limits, otherwise the run is refused with no
change. This gap was found and closed while preparing this proposal, in the deployer too.

**Representativeness gate.** The probe joins with private topics, so it does not start data flow the way recovery's real
sensor subscriptions did. The storm could therefore be milder than Stage A. The supervisor reports **PASS only if at
least 4 samples reached ≥ 95 % inside the bound** (Stage A had 5–6). A milder storm is **INCONCLUSIVE**, never PASS.

## 3. Safety observation path

The observer reads the existing `foxglove_bridge` WebSocket (subscribe-only; no new participant), the base's own runtime
odom file, and `/proc`. It evaluates every 0.25 s with 1.0 s freshness and a 1.0 s verdict-gap limit. The 11 signals are:
- E-STOP latched, manual-only, commissioning off, source STOPPED (`/atlas/control_policy`, 10 Hz);
- `cmd_zero`, all six components (`/cmd_vel`, 4.7 Hz);
- `motor_output_zero` (`/motor_speed`, **1.8 Hz, 0.37 s margin**);
- `telemetry_live` (`/atlas/encoder_health`, 10 Hz);
- base loop alive and base still (odom runtime file, ~3 Hz);
- base identity (`/proc`);
- observer connected.

The dashboard's 14-predicate `/api/status` snapshots are used only before (×3) and after (×3), as before.

## 4. Abort conditions and maximum detection latency

Every abort kills the probe's process group with SIGKILL, keeps all evidence, and results in FAIL with no retry.

| Condition | Detection |
|---|---|
| Any observer signal stale (incl. `/motor_speed`), malformed, unadvertised; bridge lost | ≤ 1.0 s freshness + 0.25 s verdict + 0.25 s supervisor loop ≈ **≤ 1.5 s** |
| E-STOP released, command or motor output non-zero, encoder fault, pose change | next message + ≤ 0.5 s (≤ 1.1 s for motor_speed) |
| Observer verdicts stop (gap > 1.0 s) | ≤ 1.5 s |
| CPU > 75 % after the 10 s bound (or at any time under `strict`) | ≤ 1 s sample + 0.25 s |
| RAM > 80 % or temperature ≥ 70 °C, any sample, inside the window too | ≤ 1 s + 0.25 s |
| Production service PID change (base, recovery, mux, safety, web, camera, EKF, localization, LiDAR, …) | ≤ 1.25 s |
| Probe alive > 15 s after spawn | at 15 s (probe self-kills at 14 s via SIGALRM) |
| Supervisor dies | probe killed at once (`PDEATHSIG`; tested < 1 s) |
| Supervisor stalls | probe exits ≤ 1.1 s after its last heartbeat (tested < 2 s end-to-end) |

## 5. Cleanup verification (automatic, part of the verdict)

- Probe PID and process group gone.
- No process with the probe in its command line.
- The DDS participant set (processes mapping `libfastrtps`; 45 in today's read-only check) is **identical** before and after, with none new and none lost.
- No new `/dev/shm/fastrtps_*` segment (145 in today's read-only check).
- 14/14 web safety predicates ×3 after the run; protected PIDs unchanged.

## 6. Offline results (container, no ROS)

The real supervisor and the real probe file run under a stub `rclpy` (records entities like Humble). The fake bridge is
a real WebSocket server. Results: see the commit message and `project_atlas/tests/test_storm_rehearsal.py`.

## 7. GO / NO-GO

- **GO to request approval of ONE supervised rehearsal.**
- **Stage A remains NO-GO** until a representative rehearsal PASSes.

The approval needs:
- the `--cpu-rule transient --transient-bound-s 10` exception, applying only to this probe;
- confirmation that motors and steering servos are disconnected and the transmitter is off;
- acceptance that a mild storm yields INCONCLUSIVE.

```
systemd-run --user --unit=atlas-stage28-storm --collect --wait --pipe -E OWNER_APPROVED=yes \
  -p WorkingDirectory=<pkg> /usr/bin/python3 stage28_storm_rehearsal.py --cpu-rule transient --transient-bound-s 10
```
