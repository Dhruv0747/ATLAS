# Permanent monitoring recovery: result (2026-11-04)

Owner approval 14:23 IST: staging and exactly one attempt of `m2-permanent-20261104`, archive
`c8ec1d39380a4a3c4d26d10ff90fbb0c67f6970c9077ba13af5321366359e649`.

## Pre-execution gates (all PASS)

- Prometheus `/-/ready`: "Prometheus Server is Ready."; Grafana `/api/health`: `database: ok` (12.1.0).
- Archive staged to the Jetson: SHA OK, 11/11 members 0644 root, 10/10 payload checksums OK; new identity
  directories absent.
- Owner start command re-checked all eight incident hashes and the exact 8-file count: all OK.
- Fresh control policy: manual_only, commission off, stop latched; cmd_vel 0, motor_speed 0, encoder
  interval deltas 0 (all age < 1 s).
- CPU 59–63 % (10 x 1 s), RAM ~59 %, hottest zone 63.6 C. Pre-existing camera publisher was already running
  (not activated by this work).

## Execution

- Start 14:25:52 IST; firewall 14:25:57, watchdog 14:26:00, exporter 14:26:04, 0 restarts.
- Worker: `Finished with result: success`, runtime 5 min 10.7 s, CPU time 9.5 s.
- Result: `{"cleanup": "NOT_NEEDED", "grafana": "OWNER_CONFIRMED", "result": "PASS"}`. No cleanup ran, so
  none of the cleanup-path daemon-reloads occurred.

Deviation: the owner's `confirm-client` was recorded before the approved 120 s target (14:27:52) and before
the assistant reported Prometheus fresh (first UP observed 14:26:17). `confirm-client` records only after
its own `verify_success()` (exporter listening, firewall, no fault, installed config hashes). The code treats
120 s as a target, not a minimum; the receipt was within its 310 s validity. Accepted by the transaction; not
the approved procedure. Follow-up candidate: enforce the 120 s minimum in code.

## Live state after PASS (read-only, 14:33 IST)

- Guard 188d53db, watchdog unit 21f8ad39, exporter unit ac991e9d (rendered 74b22487), firewall cb7f3734;
  no drop-ins; exporter/watchdog `Restart=on-failure`, 0 restarts; exporter enabled.
- Prometheus: `up=1`, scrape age < 5 s, 3 s scrape interval, exporter observation timestamp advanced 19 times
  in 5 min (15 s collector interval), `atlas_estop_latched=1`, no stale topics.
- Peaks over the run (exporter 15 s samples): CPU 63.3 %, RAM 59.0 %, temperature 63.9 C. The transaction's
  1 s sampler file is root-only and was not read.

## Acceptance

| Item | Result |
|---|---|
| Recovery transaction | PASS |
| Exporter | UP |
| Prometheus | FRESH |
| Grafana | HEALTHY (health API; panels not viewed, sign-in not used) |
| Neural pulses | BLOCKED: all 8 verified edges STALE |
| Fault archive and cleanup | PASS (cleanup not needed) |
| Automatic reconnect | UNVERIFIED |

Neural pulses: the exporter collects every 15 s (`INTERVAL_S`), and the reviewed edge rule adds collection
age to topic age against 1–5 s limits, so edges are STALE nearly all the time. This is the reviewed
behaviour ("never widen freshness just to maintain continuous animation"), not a transaction defect.
Making pulses live requires fresher data (a shorter exporter interval, which is pinned by the guard and so
needs a new reviewed transaction), not looser limits.

Reboot persistence: NOT TESTED (separate approval).
