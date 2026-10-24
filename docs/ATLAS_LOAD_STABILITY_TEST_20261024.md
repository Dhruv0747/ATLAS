# Parked load-stability test (is ATLAS healthy at ~80% CPU?) — built, offline-tested, NOT run on ATLAS

**Why:** the owner's 14:45 Depth start was blocked at 80.3% (1-s guard sample that includes Astra driver start-up;
71.0% just before). Raising the Vision Lab limit from 75% to 80% is the owner's decision; this test provides the
evidence first. It changes no limit and starts no camera.

**Tool:** `project_atlas/tools/diagnostics/atlas_load_stability_test.py` (owner approval 14:47 to build).

- Synthetic busy-loop load at **normal priority (nice 0, like the Astra driver)**, continuously adjusted so the
  whole Jetson sits at `--target` (default 80%). A nice-19 load would only fill idle time and overstate headroom.
- Phases: preflight (parked) → baseline 60 s (no load) → load 300 s → recovery 30 s → verdict.
- Records every second: whole CPU, RAM, max temperature, ages and observed rates of LiDAR/odom/IMU/4 encoders,
  cmd_vel/policy/mission/AMCL/drive PID ages, E-STOP state, dashboard response time.
- **Immediate abort** (load removed within ~1 s): E-STOP not latched, policy not stopped, commands nonzero,
  mission not READY, any required sensor older than 1.5 s, temperature ≥ 70 °C, RAM ≥ 80%, dashboard not answering
  3 s, CPU ≥ 92% for 3 s. Hard limits: target 50–85%, load ≤ 600 s. Needs `OWNER_APPROVED=yes`.
- **PASS** requires: no abort; steady load within ±3 of target; every sensor's worst age ≤ 1.0 s under load;
  sensor rates ≥ 90% of baseline; dashboard p95 response ≤ 1.0 s; temperature < 70 °C and RAM < 80% throughout.

**Offline tests** (`project_atlas/tests/test_load_stability_offline.py`, fake dashboard + fake thermal zones, real
CPU load on a 2-core x86 host): 5/5 pass — full run reaches and holds the target then removes the load; aborts
within seconds on a stale LiDAR, a released E-STOP and 70.5 °C; refuses without approval, with target > 85%, when
not parked, with a stale encoder and with < 2 °C thermal margin.

**Limits:** offline proves the controller and the abort logic, not how ATLAS behaves at 80% — that is what the
on-robot run measures. The on-robot run needs a separate approval; a later change of the 75% limit needs another.
