# Final monitoring verification and PR13 review — 2026-10-30 IST

Reviewed head eb02905782fce4085a305ec5b70d68cb4ed76428. Runtime source remains b1946bd; this review changes documentation only. No reinstall, activation, firewall change, critical restart, camera start, movement, firmware change, reboot or merge.

## Verdict

Current backend monitoring PASS; Grafana live data PASS, with presentation defects below. Firewall PASS. READY FOR OWNER REVIEW of these findings, but HOLD final merge as a completed reboot-reliable product until the readiness/display concerns are resolved or explicitly accepted as follow-up scope. Reboot testing remains PENDING, not failed or passed. No claim of days-long stability from eleven minutes of operation.

## Live evidence (20:55–20:57 IST)

- Exporter PID112521 enabled/active; watchdog PID112457 active; firewall oneshot active. NRestarts=0 for each. Journals since20:45 show startup only, no rejection/crash/restart messages.
- Current privileged owner-terminal nft JSON matches canonical guard expectations: inet atlas_monitor input priority-10; TCP9118 RETURN only on wlP1p1s0 from192.168.1.6 to192.168.1.16; subsequent TCP9118 DROP covers other IPv4/IPv6 sources. No firewall edit made. Watchdog repeats exact rule verification every second. Source filtering is not authentication of individual applications on Windows.
- SSH works; dashboard API works; Tailscale reports current Jetson/Windows peers. Current service identities: dashboard2098, mux1949, remote1982, base3258, EKF3010, localization4618, LiDAR1951, all active/NRestarts0. FlySky teleop remains inactive/PID0/NRestarts0. Known activation identities for dashboard/mux/base unchanged; no restart-counter increase for any exported service in the ten-minute history.
- Grafana authenticated datasource query epoch1793373951: up1; observed age6.06695s; CPU62.26890%; GPU0% with source availability1 (real idle reading); RAM62.60229%; temperature62.937C. All20 tracked topics available and not stale. Xbox selected1; FlySky selected0/drive-enabled0; E-STOP latched1. Astra and FlySky-status sources0 explicitly unavailable, not fabricated healthy. No new camera/sensor subscriptions.
- Forty-panel Grafana dashboard returned by API. Browser refresh rendered UP, LATCHED, observation age10.5s and FRESH sensor tables, plus CPU/RAM/temperature/GPU chart sections. Actual rendering findings below prevent claiming perfect UI acceptance.
- Prometheus/Grafana containers up, bound only127.0.0.1:9090/3000; authentication preserved. No public listener introduced by this review. Exporter remains LAN-bound, protected by nft.

## Historical stability and overhead

Latest available ten-minute Prometheus window:39 scrapes, minimum up1; CPU average61.79783%, maximum63.05040%; max temperature63.75C. RAM subquery average61.38313%, max63.13293%. Max topic-stale flag0 for all20 topics; sum service restart increases0; ALERTS empty. Scrape/collection averaging cannot establish absence of sub-second spikes. The independent guard still samples at its unchanged one-second interval.

The accepted five-minute root-checksummed evidence remains authoritative: baseline CPU61.59668% average/66.83250% peak; active61.87556% average/71.31012% peak; active RAM max63.00842%, temperature max63.812C. Observed CPU-average increase0.27887 percentage points, not an isolated causal performance experiment.

At uptime14942.79s: exporter CPU2.001739s since active14333.203729s (~0.328% of one core), memory12115968 bytes(~11.55MiB); watchdog CPU6.619516s since14329.576210s (~1.079% of one core), memory10735616 bytes(~10.24MiB). Combined ~1.41% of one core and21.79MiB. CPU accounting includes initialization and is not whole-Jetson percent. No drift/memory-leak conclusion from this short observation.

Previously verified25-second PC Prometheus outage left Jetson monitoring/protected services running and recovered afterward. Reused that evidence; did not interrupt servers or inject failures again.

## Review findings / remaining acceptance work

1. **Reboot startup is fail-closed but not guaranteed to recover automatically.** Exporter enabled under multi-user.target, firewall required before watchdog, Type=notify readiness and exporter preflight correctly prevent unprotected listening. However After=network-online.target does not itself pull in that target, and no dependency waits for the user dashboard, fresh ROS telemetry or user bus. Watchdog starts with two immediate samples and Restart=no; an early boot API/telemetry failure latches FAULT/observer state. A safe readiness design or explicit manual recovery policy is needed before claiming automatic reboot recovery. Never clear the fault or relax safety to force startup. Actual reboot not tested.
2. **Windows automatic start incomplete.** Docker enabled within systemd-enabled Ubuntu22.04 WSL; containers use unless-stopped and named volumes, but no ATLAS/WSL scheduled task was found. Prepared XML has not been registered. Windows login/WSL launch and volume recovery through reboot remain separately approved tests. Do not claim unattended Windows recovery.
3. **Dashboard presentation defects observed.** Selected controller stat shows numeric1, although verified source is XBOX. Inactive FlySky failsafe panel shows "Data does not have a time field" rather than a clear UNAVAILABLE explanation. These are display problems, not control changes. Fix and focused UI validation recommended before final UI acceptance.
4. **Viewed tab auto-refresh was off.** It displayed an older20:52 snapshot until Refresh; after Refresh it showed20:56:26 values. Provisioned JSON specifies15s, but effective browser state must be checked. Do not equate backend freshness with an automatically updating browser. No browser preference or provisioning was changed here.
5. **No external notification transport.** Rules evaluate in Prometheus; no Alertmanager configured. Empty ALERTS means none currently pending/firing, not proof every alert condition has been exercised live. Existing synthetic rule tests cover stale/missing/boundary behavior.
6. **Stationary-only scope is intentional.** Release of E-STOP, movement, commissioning or failed resource/freshness checks stops monitoring and latches review; it never changes rover controls. It is not general driving-time monitoring. Root firewall tampering has finite detection delay; existing isolated denied-source tests do not prove all future networking changes safe.
7. **Timestamp correctness:** precision defect is fixed and live ages plausible. Local expiry uses monotonic time; exported timestamp uses Unix seconds. Cross-host clock-offset accuracy has not been independently bounded in this review; NTP/clock adjustment remains a documented dependency of Prometheus age, not the local safety guard.

## Complete PR scope / validation

Reviewed changed-file inventory45 files: monitoring exporter, optional supervisor/firewall and activation tooling, dashboard/provisioning/alerts, tests, reports and documentation; only root .gitignore/README/CHANGELOG otherwise changed. No firmware, ROS node/control, white-glass UI or motor configuration diff. Exporter reads proc/sys, fixed systemctl-show units and two existing local GET APIs; no ROS participant, serial access, command publication or service-control API exposed. Supervisor controls only optional monitoring units and its owned firewall table. Password file ignored, mounted as a local secret; anonymous Grafana disabled. Reviewed rollback stops/proves listener absent before firewall removal, retains protection on ambiguity.

Focused remaining regression: timestamp and configuration suites **30 passed in0.23s** in PC WSL. Reused prior86 focused implementation tests,12 simulated activation tests,8 native packet-path checks,9 fake-systemd checks and native Promtool boundaries; did not repeat those or any full rover suite. These passing tests do not cover the newly observed display/readiness issues.

Corrected current README status and obsolete UFW allow-only/user-unit rollback instructions. Historical reports remain historical; current runbook/report take precedence. No executable or deployment artifact changed, so no package rebuild or live installation is needed.

## Rollback availability (not executed)

Local administrator command: `sudo python3 -I -B /usr/local/libexec/atlas-monitoring-guard.py rollback`.

See RUNBOOK.md for independent shutdown/owned-table removal if helper fails. Never delete firewall before proving exporter stopped; never flush/restore broad Tailscale rules. Evidence remains /var/lib/atlas-monitoring-timestamp-retry-20261030. No current safety failure requires rollback.
