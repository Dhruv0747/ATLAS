Current status: [authenticated integration preparation](INTEGRATION.md) supersedes the prototype-only limitations below. Nothing deployed.

# Pulse visualization: offline only

2026-11-02 investigation: actual installed Grafana query definitions match the reviewed dashboard. Prometheus reports atlas-jetson up=0 and atlas_topic_rate_hz has no series. Installed Grafana 12.1 Edge.tsx renders static SVG lines; no pulse-motion option is present. Missing motion is expected, not evidence of a rendering failure. Exporter outage cause remains UNKNOWN here.

The deployed Node Graph and Health Monitor are unchanged. This separate dependency-free SVG prototype reuses neural_topology.json. It has no live ingress, no credentials and no ROS/camera subscriptions. Prometheus and robot configuration are untouched. Never label its synthetic test output live.

Pulse gates: audited connection, up=1, available=1, finite positive rate, valid nonnegative topic age, query/exporter timestamp consistency, collector age under 30 seconds and topic-specific freshness. Monotonic elapsed time and conservative request duration age observations continuously. Repeated/older query snapshots are rejected, not refreshed. Hidden pages and manual/reduced-motion pause hide pulses. Fixed pulse speed represents activity, not exact packets or message rate. Full source evidence is shown when selecting a connection.

Tests: node --test monitoring/atlas/pulse-view/gates.test.mjs (3 focused tests). Existing Playwright via NODE_PATH: node monitoring/atlas/pulse-view/browser.test.cjs. Browser intercepts all requests and serves only repository assets; no HTTP server or production API involved. Browser PASS: eight moving verified pulses, no unverified pulses, stale expiry, idle, disconnect and visual pause. Desktop and 390px viewport exercised. Rendering sample: 0.0717 s idle vs 0.1899 s active renderer task time across 3 seconds each; JS heap 2.81 MiB. Synthetic PC browser evidence only, not Jetson or full-process CPU measurements.

GO for offline review. NO-GO for production deployment. Prerequisites: recover monitoring via separately approved procedure without clearing faults automatically; implement/review authenticated same-origin read-only data ingress using existing Prometheus samples with query timestamps and measured request duration; prevent cached/replayed responses renewing freshness. Keep all existing scrape intervals and topic expiry thresholds. Never widen freshness just to maintain continuous animation: 15-second scrapes with 1-second topic expiry legitimately produce long non-animated periods. Do not expose Prometheus cross-origin or turn off Grafana authentication.

No Grafana plugin installation, dashboard replacement, service restart or deployment performed. Future rollback removes only a separately approved pulse view; existing dashboards must remain untouched.

2026-11-02: offline reconnect handling now discards late responses, queries once on reconnect, and continuously ages selected-path details. See INTEGRATION.md for focused evidence and one-asset rollback. Repository-only; no deployment.
