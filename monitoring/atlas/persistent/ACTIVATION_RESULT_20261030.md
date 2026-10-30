# Controlled persistent activation — FAIL, rolled back

One owner-approved attempt used runtime 852feb9 and orchestrator 373e780. Started 2026-10-30 approximately 20:25 IST. Firewall/watchdog startup succeeded; exporter started at 20:26:10 IST. Operator Ctrl+C aborted the observation window after a confirmed timestamp integrity defect. No retry.

## Verified new findings

- Prometheus target `up=1`; actual sensor metrics arrived. Grafana authenticated dashboard API returned ATLAS HEALTH MONITOR with 40 panels; its datasource proxy returned current temperature (63.406 C) and up=1. This verifies real datasource access, not every panel's visual rendering.
- A 25-second pause of only the PC Prometheus container left Jetson monitoring and checked rover services active with zero restarts. Prometheus was unpaused in finally and readiness/scraping recovered. No Jetson service restart.
- Missing Astra and FlySky sources reported `atlas_source_available=0`, not healthy. Current live telemetry topic stale flags were zero.
- **Blocking defect:** `Out.emit()` uses `{n:g}` (six significant digits). Epoch timestamp 1793372301.702 became `1.79337e+09`, parsed as 1793370000.0: **2301.702 seconds of artificial age**. This was reproduced offline exactly. Grafana's last-successful-update expression and AtlasTelemetryStale alert both consume this metric. Prometheus reported AtlasTelemetryStale firing despite fresh data.
- The safety watchdog reads dashboard freshness directly; it does not use this rounded Prometheus timestamp. No safety threshold failed or was weakened. The attempt failed monitoring correctness validation and was deliberately interrupted.

## Measurements and limits of evidence

Live CPU metric sampled 62.195%, temperature 63.406 C. At roughly 114 seconds after exporter start, systemd recorded exporter CPU 0.680421 seconds and memory 11,624,448 bytes (~11.09 MiB). Watchdog CPU 1.393552 seconds over roughly 117.6 seconds and memory 10,612,736 bytes (~10.12 MiB). These imply approximately 0.60% and 1.18% of one core respectively over that partial interval, including startup. They are not matched whole-Jetson before/after overhead measurements or full-window averages/peaks. Complete baseline and capture samples remain root-only in the evidence directory and have not been independently read back.

## Cleanup evidence

Owner terminal returned:

```json
{"result":"FAIL","source_commit":"852feb9ad8e6443b74981cbe6d8b2e013644e330","error":"activation interrupted","rollback":"VERIFIED"}
```

Independent SSH checks after interruption:
- Exporter/watchdog/firewall units: inactive, LoadState=not-found, MainPID=0.
- Rollback timer: inactive, LoadState=not-found.
- No TCP9118 listener; installed exporter file absent.
- Dashboard PID2098, command mux PID1949, base telemetry PID3258: all active, NRestarts=0, same as before.
- Fresh policy: manual_only=true, stop_latched=true, commission_armed=false, FlySky drive disabled; linear/angular commands zero.
- Grafana database remains healthy on Windows localhost.

Wrapper reports firewall removal; a separate privileged post-rollback firewall dump has not been reread remotely. Root evidence location: `/var/lib/atlas-monitoring-activation-20261030/` (result.json, samples.json, firewall/service baselines, SHA256SUMS). Preserve it; do not clear the single-use claim or fault evidence. No persistent monitoring is left active. No camera/motor/firmware operation, rover reboot or PR merge occurred.

## Next necessary action

NO-GO for repeating this artifact. Prepare a minimal offline numeric-format fix preserving timestamp precision; regression-test timestamp round-trip and actual stale-alert boundaries, including large counters. The approved exporter hash must change for that fix, so build a newly reviewed package and request new activation approval. Do not retry automatically. Reboot persistence remains unverified.
