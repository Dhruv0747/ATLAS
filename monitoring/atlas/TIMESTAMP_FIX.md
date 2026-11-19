# Timestamp precision fix — offline, 2026-10-30

**PASS offline; not deployed.** The previous activation remains failed/rolled back. Never rerun the previous activation command.

## Confirmed cause and minimal correction

Out.emit converted numbers to float then rendered them with default `:g`, which keeps only six significant digits. The saved failure value 1793372301.702 Unix seconds became `1.79337e+09` (1793370000.0). Prometheus therefore computed a false age of **2301.702 seconds** and fired AtlasTelemetryStale; this was formatting loss, not a milliseconds/seconds or timezone conversion.

Render finite float64 values using Python repr (shortest round-trip representation). The exact saved failure now parses back to 1793372301.702 and computed age at the same instant is **0 seconds**. This also avoids rounding larger counters unnecessarily. Nonfinite/missing values remain omitted, never converted to zero.

The exported observed timestamp remains wall-clock Unix seconds from time.time(), as required by Prometheus time(). Local HTTP cache expiry now uses time.monotonic() for both storage and comparison, preventing wall-clock adjustments from extending cache freshness. Missing/malformed/negative/nonfinite timestamps and negative elapsed durations reject; 45 seconds is accepted and >45 seconds returns stale, preserving the existing boundary. Cross-host NTP/clock-offset verification remains a live acceptance requirement; no precision fix can prove clocks synchronized.

## Executed tests

- **48 passed**: timestamp regressions plus existing affected exporter/config suites, 2.02s.
- **38 passed**: affected persistent guard/package and simulated activation suites, 0.63s. No native packet/lifecycle reruns because firewall/units did not change.
- Native Promtool v3.5.0 in an isolated `--network none` PC container: `test rules /work/timestamp.test.yml` **SUCCESS**. Actual alert expressions tested fresh, exactly 45s, 45.001s and absent timestamp/exporter-down behavior. Missing age expression returns no series, not zero. No running Prometheus/Grafana service changed.
- Saved numeric failure reproduced and eliminated exactly; future epoch beyond 2038, fractions, malformed/missing values, large exact counters and local wall-clock changes covered.

No Jetson commands, exporter startup, production restart, firewall change, E-STOP/motor/firmware/controller change or activation retry was performed for this fix.

## Review package identity

Offline rendered UID1000 review package: `/tmp/atlas-timestampfix-review-20261030` in PC WSL. Verify the actual Jetson UID afresh before future deployment.

- Fixed exporter artifact SHA256: `0248d329dd659f3557b68ae8731cb1a85db763bb7855850e1c5cec0ccd0f3e3d`
- Package SHA256SUMS SHA256: `155bb0074f653a7a3846bac120f5284f1be458952eb2831ebc8f32a39e882c27`
- Guard and package-builder expected exporter hash updated only to identify this reviewed candidate; all safety predicates, thresholds, firewall rules, ordering and resource limits remain unchanged.
- Historical trial hashes/reports are retained as history, not rewritten to claim this candidate was live-tested.

**Readiness:** software fix and review package ready for separately approved retry. Existing activate_once.py deliberately still pins the OLD manifest and its consumed single-use evidence directory; it must not be used for this candidate. Before any new approved operation, prepare a new hash-pinned single-use command/evidence location, preserve prior rollback evidence, and recheck fresh safety/UID/firewall state. Approval must explicitly cover this new exporter SHA. Actual live Grafana age/alert behavior and reboot persistence remain PENDING.
