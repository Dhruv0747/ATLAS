# Grafana UI fixes — 2026-10-30

PASS: changed only generator/generated dashboard, focused tests and documentation. Provisioned only the JSON in PC WSL /opt/atlas-monitoring/grafana/dashboards/atlas-health.json; Grafana picked it up without restart. No Jetson operations performed.

- Authoritative atlas_control_selected is one-hot by controller label, not a numeric controller ID. Query derives display values XBOX1 / FLYSKY2 from those verified labels. Missing/unmapped-only data falls back to-1 UNAVAILABLE; conflicting known selection totals3 UNKNOWN. No controller configuration changes.
- FlySky failsafe/frame-lost current-status panel now uses instant stat fields. Absent series maps to-1 UNAVAILABLE, while genuine0=clear and1=SET remain distinct. Historical remote-control panels retained.
- Dashboard default30s: browser interval menu supported5/10/30 seconds but not15; the previous15s selection fell back to OFF. Browser30s selected and persisted dashboard API refresh30s verified. Prometheus scrape interval remains15s; no backend configuration changed.
- Actual browser: Selected controller XBOX; FlySky panel failsafe UNAVAILABLE and frame lost UNAVAILABLE, without time-field error; refresh control30seconds selected. Source policy remains XBOX; FLYSKY not physically activated for this display test.
- Focused dashboard/config tests9 PASS in0.15s, including regenerated-JSON equality, authoritative-label mapping, missing fallback, interval and unchanged scrape/limits/private ports. Existing runtime safety tests not rerun.
- Live Prometheus query returns controller derived1; both absent FlySky values-1. No fake metrics written. No threshold, exporter, watchdog, firewall, ROS, firmware, motion or authentication changes.

Rollback JSON backup on PC WSL: /opt/atlas-monitoring/atlas-health-before-ui-fix-20261030.json. Restore only dashboard JSON from this backup if needed; no service restart required. Local reviewed screenshots retained outside git as grafana-controller-fixed.png and grafana-flysky-fixed.png in workspace work/.

No PR13 merge. Reboot readiness/Windows startup task remain separate previously documented concerns; these UI fixes do not establish reboot persistence.
