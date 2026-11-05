# Proposal: tolerate encoder jitter in the monitoring guard (NOT INSTALLED)

**Status: proposal for the owner's review. Nothing here has been applied to the Jetson.**

## Problem

On 2026-11-04 at 18:40 IST, `/usr/local/libexec/atlas-monitoring-guard.py` (watchdog) latched with
`encoder movement`. At that moment:

| | M1 | M2 | M3 | M4 |
|---|---|---|---|---|
| previous | 4 | -8 | -19 | -1 |
| now | -1 | -2 | -28 | 6 |
| delta | -5 | +6 | -9 | +7 |

`stop_latched=true`, `manual_only=true`, `commission_armed=false`, `cmd_vel=(0,0)`, `motor_speed=0`. The deltas
are small, go in mixed directions and have no command behind them, so they look like encoder jitter. The owner
confirmed the rover was stationary. Because the latch persists in `/var/lib/atlas-monitoring/FAULT.json`, the
firewall refused at 12 consecutive boots. The exporter and watchdog never started, so Grafana and the
neural/Pulse view showed no data after any reboot. The latch was cleared after owner review on 2026-11-05
(the original is kept as `FAULT.reviewed-20261105.json`).

## Proposed change

The change applies to `check_violations()` (current lines 219–224) and to the duplicate check in `validate()`
(line 240). A wheel's count may change by **at most `JITTER_COUNTS` per sample**, and **only** while the same
sample has already passed every "stopped" check (policy latched/manual/not commissioned, `cmd_vel` exactly 0,
`motor_speed` exactly 0; those checks run earlier in the same function and raise first). In addition, the
**cumulative** change from the first sample of the observer run may not exceed `DRIFT_COUNTS` on any wheel.
That catches a slow push that stays under the per-sample limit.

```python
JITTER_COUNTS = 10   # per wheel, per ~1 s sample, only when commanded/actual speed is exactly zero
DRIFT_COUNTS = 40    # per wheel, cumulative from the observer's first sample

# check_violations(): replace the per-wheel "now != before" test
    if previous is not None:
        for (ok, now), before in zip([present('enc_m'+str(i)) for i in range(1, 5)], previous):
            if ok and type(now) is int and type(before) is int and abs(now - before) > JITTER_COUNTS:
                raise Violation('encoder movement')

# validate(): replace  require(previous is None or counts == previous, 'encoder movement')
    require(previous is None or all(abs(a - b) <= JITTER_COUNTS for a, b in zip(counts, previous)),
            'encoder movement')
    # baseline = counts from the first validated sample of this observer run (kept by the watchdog loop)
    require(baseline is None or all(abs(a - b) <= DRIFT_COUNTS for a, b in zip(counts, baseline)),
            'encoder movement')
```

The watchdog loop (around line 293) needs to keep `baseline` (set once, at the first successful
`validate()`) and pass it to `validate()`.

## What does NOT change

- Any non-zero `cmd_vel` or `motor_speed`, or a policy that is not stopped/manual: immediate latched violation,
  as now.
- A per-wheel jump over 10 counts in one sample, or more than 40 counts in total: latched violation, as now.
- Freshness, CPU 75 %, RAM 80 %, MCU-live, firewall ownership and exporter hash checks: unchanged.
- Latches still persist and still need owner review.

## Values to confirm before installing

`10` and `40` are starting points based on the one observed event (max |delta| = 9). Check the counts per
wheel revolution for this Yahboom base. 40 counts should be a small fraction of a wheel turn. If it isn't,
lower `DRIFT_COUNTS`.

## Install (owner, on the Jetson, rover stationary with E-STOP latched)

1. `sudo cp -p /usr/local/libexec/atlas-monitoring-guard.py /usr/local/libexec/atlas-monitoring-guard.py.before-jitter`
2. Edit as above, then `sudo python3 -I -m py_compile /usr/local/libexec/atlas-monitoring-guard.py`
3. `sudo systemctl restart atlas-monitoring-watchdog` (the exporter is bound to it and restarts with it).
4. Rollback: copy the `.before-jitter` file back and restart the watchdog the same way.
