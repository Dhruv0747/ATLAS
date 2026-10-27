# Stage 28 — independent safety observation during DDS CPU saturation (offline + read-only), 2026-10-27

Status: designed, offline-tested, read-only verified against the real `foxglove_bridge` at idle.
**Not validated against a real discovery storm. Stage A: NO-GO.**
No deployment, no service restart, no threshold change. Jetson access: read-only commands, two short observer runs
(subscribe-only).

## 1. Confirmed failure mechanism (Stage A attempt 2, 21:54:45)

**Confirmed (evidence):**
- At +4.52 s after the recovery restart, with CPU at 98.5–99.8 %, the deployer's `GET /api/status` hit its 2 s timeout.
  `rover-status-web` logged the matching `BrokenPipeError` at 21:54:45.9.
- In the same snapshot, `GET /api/estop/state` answered.
- The previous snapshot (+0.61 s, CPU 71 %) answered fully.

**Confirmed (code, `atlas_status_web.py` live c.f. 4ab16214):**
- `/api/status` → `snapshot()` refreshes a "slow cache" **synchronously inside the request, under a lock**, every ≥ 2 s.
  The refresh spawns three subprocesses: `ip -4 -br addr`, `ip -j route get`, `ss -tn` (2 s timeout each). It then
  builds the full ~150-key ROS snapshot.
- `/api/estop/state` only reads cached ROS items.

**Not confirmed:** whether fork/exec delay or GIL starvation inside the web dominated. The web runs a
107-subscription rclpy executor that receives discovery work in the storm. An offline replica (Python HTTP server,
GIL-busy threads, the same three subprocesses) did **not** reproduce a > 2 s timeout under 1–8× CPU
oversubscription (max 1.09 s). Plain oversubscription is fair-shared; the real storm adds work *inside* the busy
processes.

**Scheduling facts:**
- RLIMIT_NICE and RLIMIT_RTPRIO are 0 for user `jetson`, so no monitor can be given higher priority without a system change.
- The user manager has no `cpu` controller, so `CPUWeight` is not enforced.
- `/proc/<pid>/io` does not exist on this kernel, so serial byte counters are unavailable.

## 2. Proposed architecture: `atlas_safety_observer.py` (deployer-side, read-only)

```
mux ──/atlas/control_policy 10 Hz─┐
mux ──/cmd_vel 4.7 Hz─────────────┤     existing foxglove_bridge (C++, port 8765,      ┌──────────────────────────┐
base ─/motor_speed 1.8 Hz─────────┼──▶  existing DDS participant; subscribe-only) ──WS─▶│ atlas_safety_observer    │
base ─/atlas/encoder_health 10 Hz─┘                                                    │  verdict every 0.25 s,   │
base ─ writes atlas_yahboom_odom_state.json ~3 Hz (runtime file) ───────────────────▶ │  freshness by LOCAL      │
kernel ─ /proc/<base pid>/stat (identity, not zombie) ───────────────────────────────▶ │  arrival time            │
                                                                                       └──────────┬───────────────┘
                                         deployer ObserverRecorder: warm-up 3 s continuously OK before the restart;
                                         any not-OK verdict or verdict gap > 1.0 s → IMMEDIATE ABORT → rollback
```

- **No new DDS participant.** Subscribing adds 4 endpoints to the bridge's existing participant.
- **No serial access, no ROS code, no HTTP dashboard dependency in the window.** Standard library only; the Jetson
  has no websocket package. Bridge 3.4.2 subprotocol `foxglove.sdk.v1`, falling back to `foxglove.websocket.v1`.
- **Before and after the window:** the existing 14-predicate web snapshots stay unchanged.

## 3. Source of every safety signal

| Signal (fail-closed) | Actual source | Producer | Rule | Measured interval at idle (p50 / max over 30 s) |
|---|---|---|---|---|
| estop_latched | `/atlas/control_policy` via bridge | atlas_cmd_vel_mux (E-STOP owner) | `stop_latched is True` | 0.100 / 0.113 s |
| manual_only, commission_off, source_stopped | same message | mux | `manual_only is True`, `commission_armed is False`, `source == 'STOPPED'` | same |
| cmd_zero | `/cmd_vel` via bridge | mux output | all six Twist components `== 0.0` (stricter than the web's lin/ang) | 0.206 / 0.258 s |
| motor_output_zero | `/motor_speed` via bridge | yahboom_base | `== 0.0` | 0.592 / 0.627 s |
| telemetry_live | `/atlas/encoder_health` via bridge | yahboom_base | state READY/HEALTHY/DEGRADED, `packet_fresh`, `packet_age_s ≤ 1` | 0.100 / 0.128 s |
| base_loop_alive | mtime of `/run/user/1000/atlas_yahboom_odom_state.json` | yahboom_base | rewritten ≤ 1.0 s ago | 0.21–0.41 s |
| base_still | x / y / yaw in the same file | yahboom_base | within 1 mm / 0.002 rad of window start | — |
| base_identity | `/proc/<base pid>/stat` | kernel | same PID and start time, not zombie | — |
| observer_connected | WebSocket session | bridge | connected, no protocol error | — |

The E-STOP semantics are preserved: the observer reads the same mux policy fields the web and the deployer already
used. Missing, stale (> 1.0 s), malformed CDR or JSON, unadvertised, or disconnected all fail.

## 4. Freshness and maximum detection latency

| Event | New observer | Previous path (`/api/status`) |
|---|---|---|
| Value change (E-STOP release, non-zero command, encoder fault) | next message + ≤ 0.25 s; tested ≤ 0.6 s (motor ≤ 1.1 s at 1.8 Hz) | ≤ 1.5 s poll + up to 2 s request |
| Source or topic stalls | 1.0 s freshness + ≤ 0.25 s tick; tested ≤ 1.4 s | 1.0 s age at the web, but snapshot every 1.5 s, request up to 2 s |
| Monitor itself stalls (verdict gap) | **1.0 s** gap limit, checked every 0.5 s → abort ≤ 1.5 s | 3.5 s gap limit |
| Bridge crash | < 0.6 s (tested) | n/a |

The new limits are equal to or stricter than before; nothing is relaxed.

## 5. Offline and read-only results

- **Read-only on the real Jetson** (21:55–22:20, idle, subscribe-only):
  - all 11 signals decoded from the real sources;
  - 38/40 verdicts OK in 10 s; the 2 not-OK verdicts were warm-up, before the first messages arrived;
  - 30 s run: worst intervals as in §3; transport latency 0.06–0.10 s;
  - CPU during the subscription 65.0–70.4 % (no breach).
- **`test_safety_observer.py`, 11 tests:** real sockets and processes against `sim/fake_foxglove.py`:
  - value faults, stalls, malformed CDR/JSON, bridge crash;
  - unadvertise (signal fails and recovers only on re-advertise and fresh data);
  - missing topic, wrong encoding, subprotocol fallback/refusal, no bridge;
  - odom stall, pose change, base process replaced.
- **`test_base_maintenance.py`, 46 tests:** including `ObserverRecorder` warm-up, exempt signals, construction failure → refusal, and the 1.0 s gap limit.
- 57/57 pass on Python 3.10 and 3.13.
- **Synthetic saturation** (`sim/observer_saturation.py`, 30 s per level, 2-vCPU container, busy processes at the same
  nice, Python fake bridge as publisher):

| Busy procs per CPU | Observer OK fraction | Max verdict gap | Worst signal age | Web replica /status max | /estop max |
|---|---|---|---|---|---|
| 0 | 1.000 | 0.254 s | 0.592 s (motor) | 1.087 s | 0.126 s |
| 1 | 1.000 | 0.269 s | 0.592 s | 0.245 s | 0.130 s |
| 2 | 1.000 | 0.288 s | 0.587 s | 0.297 s | 0.104 s |
| 4 | 1.000 | 0.269 s | 0.595 s | 0.481 s | 0.341 s |
| 8 | 1.000 | 0.276 s | 0.622 s | 0.657 s | 0.369 s |

- **Real-systemd end-to-end simulation:** the observer is the in-window source for stage A and B. New s14: E-STOP
  released 1 s into the stage A window → immediate abort, original restored. See the commit message for the scenario results.

## 6. Remaining risks

1. **Not validated against a real discovery storm (blocking).** In Stage A the storm loads the *producers*:
   - mux and base are Python rclpy nodes that also process discovery;
   - `foxglove_bridge` was itself a top peer consumer in the web-restart traces (+10–23 % of a core).

   If any of them delays a message past 1.0 s, the observer fails closed and Stage A aborts again. That is safe, but
   it still blocks the deployment. Synthetic oversubscription does not reproduce this, which is the same reason the
   web replica did not fail.
2. `/motor_speed` arrives at 1.8 Hz: only 0.37 s margin to the 1.0 s limit. It is the most likely false abort.
3. The bridge advertises a `clientPublish` capability to any LAN client. This is pre-existing and not changed here.
   The observer never advertises or publishes.
4. Subscribing adds 4 endpoints to the bridge participant (about 1 core-s of peer discovery, spread). Measured at idle:
   CPU ≤ 70.4 %. In the deployer this happens during the strict pre-restart window, so it is gated by the existing strict check.
5. `base_still` uses a new tolerance (1 mm / 0.002 rad) on the base's own odom file. Encoder-count stillness stays in
   the pre/post web snapshots.
6. Stage B: base-owned topics will be unadvertised while the base restarts. Those signals fail and are exempt only
   while the base is down; they must recover with fresh data. Not exercised against the real bridge.

## 7. GO / NO-GO

**Stage A deployment: NO-GO.** The monitoring path has not been validated against the CPU saturation observed in
Stage A. No deployment approval is requested.

**Proposed validation (needs separate approval; no service restart, no file change).** A storm rehearsal:
- run the observer, the continuous CPU recorder and a passive per-process recorder;
- then start one short-lived *test* participant that creates the same ~32 endpoints as recovery and exits after
  15 s, reproducing exactly the Stage A join (and leave) storm;
- abort criteria: the same as Stage A (CPU > 75 % tolerated only ≤ 10 s, RAM/temperature strict);
- measured outcome: observer verdict continuity, per-topic intervals of the real producers, and bridge latency during the storm.

Stage A can be reconsidered only if the rehearsal shows every signal staying fresh (≤ 1.0 s) through the storm.
