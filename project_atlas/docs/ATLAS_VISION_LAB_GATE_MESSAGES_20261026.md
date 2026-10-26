# Vision Lab: clear stationary-gate refusal messages (26 Oct 2026)

## Problem
On 26 Oct the 3D Vision Lab refused to start with `stale or missing cmd_vel`. The Astra Pro was working
(CONNECTED on USB 2.3.4). The real cause: E-STOP was released. With the latch released and nobody driving, the
mux sends no zero-speed keepalive (it sends one every 0.2 s only while latched), so the stationary gate
(`tools/vision3d/stationary_gate.py`) saw a stale command stream (189 s old) and refused correctly. The wording
did not tell the operator what to do.

## Change (text and error handling only)
`scripts/atlas_vision3d_runtime.py`: the worker records the last safety snapshot it already fetched and, after the
gate has refused, `operator_message()` (pure function) explains the refusal:

| Gate refusal | Fresh policy says | Shown to the operator |
|---|---|---|
| stale command stream, or `stationary policy admission failed` | E-STOP **released** | ATLAS is not parked. Press B on the remote to engage E-STOP, wait 2 seconds, then start 3D Vision Lab. |
| stale command stream | E-STOP **latched** | ATLAS cannot confirm zero speed. Check the drive safety status before starting 3D Vision Lab. |
| anything else (policy unknown/stale, nonzero command, resource limits, lease…) | — | unchanged wording |

- The raw gate reason is preserved: `lifecycle[].session_stopping.reason` and `diagnostic_reason`.
- `web/v2/vision3d_state.js` shows `operator_message` verbatim (title "Not started", or "Stopped safely" when a
  running session was stopped by the same gate).

Unchanged: `stationary_gate.py` (sha 0c5ec244, test-pinned), the gate decision, 75/80/70 limits, CPU window rules,
E-STOP and mux behaviour, motor/navigation code, `cmd_vel` timing. Nothing engages E-STOP, retries or starts the
camera after a refusal. The runtime still contains no `cmd_vel` / control interface strings (existing
independence test).

## Tests
- New `tests/test_vision3d_gate_messages.py` (15 tests): helper mapping, simulated worker with the REAL gate policy
  check (E-STOP released → refused before camera launch; latched + stale → zero-speed text; released mid-session →
  camera stopped; parked session completes with no message; resource block unchanged), dashboard text under Node,
  gate file hash pinned.
- `tests/test_vision3d_stage31b_guard.py` Sim gained an optional `ros=` argument (default unchanged).
- Full suite (`pytest -s`): 1093 passed, 84 failed, 20 skipped. Every failure also fails on the untouched HEAD
  (91 failed there); no new failure. Note: the simulated-worker tests need `-s` (they read stdin).

## Deployment (26 Oct 2026, 12:0x IST)
- Preconditions: Vision Lab OFF, no Astra process, no viewer worker.
- Backup + rollback: `~/project-atlas-migration/vlmsg_20261026/` (`backup/` = runtime 5ad300f2, state.js bedbeed1;
  `rollback.sh`).
- Installed: runtime 47842ad1 (CRLF preserved), vision3d_state.js 2b071973. No service restart: the worker is a
  fresh process per Start and the JS is static.
- Live check (E-STOP released at the time, verified fresh before the click): one Start in the real page →
  CHECKING → OFF in <1 s, title "Not started", the E-STOP text above, `diagnostic_reason` `stale or missing cmd_vel`,
  `driver_pid` null, no Astra process afterwards. Screenshot: `docs/evidence/vision_lab_estop_refusal_20261026.png`.
- The latched-but-stale case is not reproducible on the parked rover without disturbing the mux; covered offline.
