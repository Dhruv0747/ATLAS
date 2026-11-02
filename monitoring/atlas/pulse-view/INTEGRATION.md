# Authenticated pulse integration preparation — 2026-11-02

GO for a separately approved PC-only installation; NO-GO for live traffic acceptance until monitoring is safely restored. Nothing deployed during this preparation. Existing Node Graph, 40-panel Health Monitor, scrape configuration and robot settings are unchanged.

## Connection and privacy

The view uses Grafana 12.1's supported GET `/api/datasources/proxy/uid/atlas-prom/api/v1/query` with same-origin session cookies. No API token/password is embedded or stored by JavaScript. No direct Prometheus connection, CORS change, anonymous authentication or plugin is required. The static shell contains no private observations; the data API enforces Grafana authentication and datasource access.

One combined instant query per 30 seconds; no overlap, 2-second abort, no redirect following, no-store cache mode. Exact job/instance, unique series, finite numeric data and up-sample freshness are checked. Exporter time is compared with server query time; the authenticated HTTP Date also bounds cached responses conservatively. Monotonic receipt age continues to expire data between polls. Wrong source, duplicates, replay, missing fields, invalid clocks, authorization denial and request failure cannot enable animation. Hidden/offline windows stop motion. No new ROS/DDS or image subscribers.

The eight audited paths alone can animate. Existing per-topic expiry and positive-rate gates remain unchanged. Pulse speed means activity, not individual packet count. With 15-second scraping and 1-second expiry on several topics, motion can legitimately be brief or absent; do not widen expiry or poll the rover to make animation continuous. Offline injection is exposed only with an explicit `?offline=1` URL and an OFFLINE TEST DATA banner, never in normal mode.

## Focused evidence

- Six Node tests PASS: state gates, malformed/missing data, clock/transport ageing, exact source identity, duplicate rejection, authenticated request configuration and cached-response rejection.
- Edge Chromium browser integration PASS: fresh, idle, stale, exporter down, HTTP 401 and timeout; 19 nodes retained; desktop 1280x900 and mobile 390x844 (horizontal graph scrolling, no page overflow); no production test-injection global.
- Motion browser PASS: eight moving paths, twelve non-animated unverified paths; automatic expiry, disconnect and pause. Latest sample: idle renderer task 0.0350 s / 3 s; active 0.0458 s / 3 s; JS heap 2.82 MiB. Synthetic local-browser sample, not whole-PC utilization or Jetson overhead.
- Existing production Grafana datasource proxy, read-only: anonymous 401, authenticated 200. Combined query syntax accepted; current result has up, query clock and up-sample time but no exporter observations. Therefore no live animation PASS claimed.
- No production static files were installed. Existing offline browser tests intercept all network requests.

## Minimal deployment proposal (NOT EXECUTED)

Archive: `C:\Users\Dhruv\AppData\Local\ATLAS\pulse-integration-20261102.tar.gz`

SHA256: `cfdca8aa8e97eb58e25803fc3ac821a69208f48034231cffc2ad17f810c6b5ce`

Five payload files plus SHA256SUMS: four pulse-view assets and the unchanged canonical topology. No models, credentials, tests, dashboards or robot files.

After separate approval: verify archive and internal manifest, record current Grafana container identity and dashboard hashes, refuse an existing destination, then copy only the `atlas-pulse` directory to `/usr/share/grafana/public/atlas-pulse` inside the existing Grafana container. Example from the verified extracted directory: `docker cp atlas-pulse atlas-monitoring-grafana-1:/usr/share/grafana/public/`. No restart needed. Proposed authenticated-data URL: `http://127.0.0.1:3000/public/atlas-pulse/pulse-view/index.html`. Verify anonymous API denial, logged-in data handling and dashboard hashes before accepting.

Rollback removes only that newly installed directory after checking its manifest and exact path; preserve existing dashboards and all provisioning. Do not restart Grafana for rollback. Container restarts preserve its writable layer, but container recreation discards these assets. A persistent bind mount/custom image would require separately reviewed configuration; do not silently modify Compose. Keep the local archive for recovery. No public/mobile-network exposure is proposed.

## Exporter fault: confirmed trigger, underlying physical cause UNKNOWN

Owner-provided retained evidence identifies watchdog rejection at **2026-10-31 18:40:47 IST**, reason `encoder movement`: M2 changed -126 to -127, other counts unchanged. E-STOP latched, manual-only true, commissioning false; zero command/speed; fresh observations. CPU 61.726%, RAM 64.119%, maximum temperature 63.062 C. Thus this rejection was not resource overload.

Subsequent firewall startup refusals explicitly say `fault latched; owner review required`. Current read-only service inspection: firewall failed exit78, exporter/watchdog inactive. This explains the missing listener and monitoring outage. It does not establish actual wheel movement versus jitter or another encoder cause; do not weaken the stationary guard. This retained October 31 fault does not resolve the earlier October 30 UNKNOWN fault.

Some later events have wall-clock values near 40 seconds since epoch, indicating invalid/unset early-boot wall time; their ordering must use boot IDs and monotonic records, not invented calendar dates. All evidence and latch remain untouched. Next recovery gate is owner review of the one-count change and fresh stationary safety verification, followed only by separately authorized monitoring rearm. No automatic reset/restart.

API reference: https://grafana.com/docs/grafana/latest/developer-resources/api-reference/http-api/api-legacy/data_source/
