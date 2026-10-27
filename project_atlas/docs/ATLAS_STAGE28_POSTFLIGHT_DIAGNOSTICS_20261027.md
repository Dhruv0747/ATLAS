# Stage 28: postflight safety diagnostics for the B1 maintenance wrapper

2026-10-27. Offline change only. Nothing deployed, no service restarted, no MCU access.
Follows `9834093` (failed `b88a569` retry, rolled back).

## What the failed retry can and cannot tell us

The rejection came from `Interlock.safe(status)` (elapsed=0) inside the wrapper's `safety()`.
Only these inputs make it return False:

| Predicate | Fails when |
|---|---|
| `control_policy` / `cmd_vel` freshness | `age` missing, not int/float (bool excluded), NaN/inf, negative, or **> 1 s** |
| E-STOP | `stop_latched is not True` |
| manual-only | `manual_only is not True` |
| commissioning | `commission_armed is not False` |
| control source | `source != 'STOPPED'` |
| zero command | `cmd_vel.value.lin` or `.ang` missing, non-numeric, or `!= 0` |
| shape | `ros`, `control_policy`, `cmd_vel` missing, or policy JSON unparsable (any exception, then False) |

The old wrapper kept no snapshot, so **the root cause is not demonstrable**. What is known:

- The failure was the first postflight sample, about 3 s after `atlas-sensor-recovery` was restarted.
  The candidate recovery had logged READY by then.
- Before (preflight) and after (rollback), every predicate passed.
- A 20 s read-only sampling at 5 Hz afterwards showed maximum ages of 0.1 s (policy) and 0.2 s (cmd), with no API errors.
- The live stop source stayed `REMOTE STOP: joystick unavailable` / `STOPPED` throughout.

The most likely class is a transient freshness failure (age > 1 s) or transient API shape. That is a hypothesis, not a finding.

## Change (wrapper only; gate, thresholds and runtime candidate unchanged)

`tools/diagnostics/stm32_readback/deploy_maintenance_once.py` (sha256 `6f761ef4…`):

- **`safety(phase)`** fetches `/api/status` with a bounded read (256 KiB) and records:
  - phase, sequence, wall and monotonic request/response/evaluation times, evaluation delay;
  - HTTP status, byte count, and any API error (timeout, refused, malformed or oversize JSON);
  - the **complete redacted snapshot**.
- **`evaluate_safety`** records each predicate separately, with its raw observation and reason:
  - `control_policy_fresh`, `cmd_vel_fresh`;
  - `estop_latched`, `manual_only`, `commissioning_disarmed`, `control_source_stopped`;
  - `zero_command`;
  - `*_present`, `control_policy_parse`, `api_shape`, `api_available`.
- **`Interlock.safe` remains the authority.** Verdict = gate True **and** no failed predicate.
  - If the gate rejects but every diagnostic predicate passes, the result is `gate_consistency` failed.
  - A gate that wrongly says True cannot pass a bad sample.
- `packet_counter` (encoder progress) rejections are recorded as `encoder_packets`. Previously they left no evidence either.
- **Evidence handling:**
  - Every sample, PASS or REJECT, goes to `evidence/safety-samples.json`.
  - Each rejection also goes to `evidence/safety-rejection-NNN.json`.
  - All writes are atomic (temp file, fsync, rename, directory fsync), then re-read and SHA256-verified.
  - `result.json` is written the same way and lists every evidence file and hash.
  - `result['safety_rejection']` names the failed predicates before the rollback starts; rollback never touches `evidence/`.
- **Evidence failures:**
  - Rejection plus evidence-write failure: still rejects, and the message says `EVIDENCE NOT SAVED`.
  - PASS that cannot be evidenced: `EvidenceError`, so it is treated as a failure.
  - `result.json` write failure: exit code 2.
- **Redaction:** keys matching password/secret/token/auth/cookie/session/credential/api-key/private/challenge/psk/ssid/bearer; IPv4/IPv6/MAC; Tailscale/GitHub/Slack-style tokens. Safety fields and hh:mm:ss times are untouched.
- The CLI also refuses a staging directory that already has `evidence/`.

`B1_DIAGNOSTIC_RETRY_PACKAGE.json` records the new wrapper hash. The runtime candidate (`8736c73`, `candidate.tar a28c5ea6…`), the thermal reader and the baseline archive are unchanged.

## Tests

`tests/test_b1_postflight_diagnostics.py`, 32 tests:
- good snapshot;
- each single predicate, with E-STOP released, nonzero/bool/None commands, wrong mode, commissioning armed, and stale, None, negative, NaN and inf ages;
- missing fields and unparsable policy;
- API timeout, refused, malformed, empty and oversize responses;
- multiple simultaneous failures;
- exact 1.0 s boundary;
- gate disagreement and gate exceptions;
- encoder rejection;
- redaction;
- snapshot write failure, plus atomic/verified writes;
- full transaction where postflight rejection rolls back and keeps hash-verified evidence;
- CLI refusal.

The existing wrapper, interlock, prompt, recovery-isolation, readback and sensor-recovery suites still pass. Result: **157 passed**.
