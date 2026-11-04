# Monitoring CPU admission: systemd double-reload correction — 2026-11-03 (offline)

Monitoring recovery remains BLOCKED. Every earlier attempt is consumed. No package was built, staged
or executed. The M2 fault evidence and the CPU <75 %, RAM <80 %, temperature <70 °C limits are unchanged.

## Evidence (read-only, 2026-11-03)
- **Steady state is under the limit.** The 1 s CPU windows (the sampler's own method) were 59–64 % over
  60 s (p50 61.5, max 64.0), with none at or above 75 %.
- **The sampler's API fetch is not the cause.** Repeating its `/api/status` fetch inside each window gave
  max 64.7 % (38 KB response, 7–62 ms). That hypothesis is rejected.
- **The rejection happens during a configuration step.** `m2-permissions-20261102` (2 Nov, 22:36:11, journal)
  failed with `G.Rejected: CPU limit` at `worker` line 428 → `supervised` → `sample`, 4.6 s after start. The
  three admission samples before it had passed. Line 428 is `supervised(prepare_override)`, which ran
  `systemctl disable` (an implicit PID-1 reload) followed by `systemctl daemon-reload`: two back-to-back
  reloads under the strict sampler.
- **The restore step has the same pattern:** `daemon-reload` and then `enable`, which reloads implicitly.
- **systemd confirms it.** On both the Jetson (249) and the development host (255), `--no-reload` means
  "Don't reload daemon after en-/dis-abling unit files".

**Status:** the location of the rejection is CONFIRMED; reload load as the mechanism is a HYPOTHESIS. The
measured CPU value is in the root-only `failure.json` of `m2-permissions`, which this correction recorded
but which has not been read yet.

## Correction (`recover_once.py` only)
- `prepare_override`: `systemctl disable --no-reload`, then the drop-ins, then a single `daemon-reload`.
- `restore_configuration`: remove the drop-ins, then `systemctl enable --no-reload`, then a single `daemon-reload`.
- The end state is the same, with half the reloads. The guard, sampler, limits, firewall, archive/reset and
  rollback are unchanged. `guard.py rollback` (`disable --now`, live-pinned) is not changed.
- `RECOVERY_SHA256SUMS`: `recover_once.py` is now `4c0bc7f1…`.

## Validation
- 62 focused checks pass (recovery transaction and CPU-evidence suites).
- The new assertion requires `--no-reload` on every enable/disable and exactly two reloads per successful
  transaction. It fails on 7bc3157 (5/5) and passes on this change.

## Remaining before any new attempt (separate approval)
1. Owner reads `/var/lib/atlas-monitoring-recovery-m2-permissions-20261102/failure.json` (sudo, read-only).
   - If the recorded CPU is only slightly above 75 %, this correction is the right size.
   - If it is far above, halving the reloads is not enough, and the owner must decide on baseline load.
2. A new single-use package with a fresh identity and the then-current verified fault hashes.
3. Fresh safety checks, then separate execution approval. No automatic retry.

## Confirmation — 2026-11-04 (owner sudo read plus journal, read-only)
- `m2-permissions` `failure.json`: CPU **78.37 %** against a 75 % threshold. Valid sample, 1.027 s interval,
  RAM 64.1 %, max temperature 63.2 °C, stage `admission_validate`. Until the firewall is verified, the same
  admission sampler also runs during `prepare_override`.
- Jetson journal, PID 1: `Reloading.` at 22:36:10.947 and again at 22:36:11.697, each taking about 0.4 s.
  The rejected window (about 22:36:10.96–11.99) contains **both** reloads. A third reload at 22:36:12.598
  is the cleanup's restore.
- Size: 78.4 % against a baseline of about 61.5 % is roughly 17 points, about 8.5 points per reload.
  With one reload the expected peak is about 70 %, roughly 5 points under the limit.

**The cause is CONFIRMED.** The correction is the right size, but only with a small margin. Whether a single
reload stays under 75 % has to be measured during the next approved attempt; there is no live proof yet.
