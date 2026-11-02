# Reliability and neural view â€” preparation only
Issue #17 reviewed 2026-11-02; main e488509. No deployment, restart, fault reset or firewall change.

## Failure separation and recovery
- Windows/WSL absent: logon task is unregistered per #17. Existing prepare-windows-task.ps1 only generates XML. Register only after owner approval. WSL systemd/Docker boot readiness must be verified separately; sleep infinity alone is not stack readiness.
- Docker failure: existing unless-stopped policies and named volumes preserve restart/data behavior after Docker starts. Inspect container health/logs; do not claim host recovery from container policy alone.
- Network loss: scrape up=0; no automatic Jetson restart. Prometheus resumes scrapes when network returns. Never classify up=0 alone as exporter crash.
- Exporter fault: inspect unit exit and watchdog state; bounded existing restart policy remains.
- Safety latch: preserve FIRST FAULT and later refusal evidence. Never auto-clear. Original reason remains UNKNOWN; owner-reviewed rearm only.
- Authorization: Grafana anonymous access remains off, ports remain localhost, Jetson source restriction unchanged. Mobile access is not enabled by this change; requires approved authenticated private access design.

## Implemented dashboard
Separate UID `atlas-live-neural-data-flow`, built-in Node Graph, 19 component nodes, eight source-audited cache-observation edges and twelve explicitly unmeasured relationships. Thirty-second refresh; scrape interval unchanged. Click-through links target topic history and the existing Health Monitor. No plugins, runtime workers, ROS participants or camera subscribers added.

Fresh positive measured rates are green, valid zero rates IDLE blue, aged observations STALE amber, missing data UNAVAILABLE grey and unmeasured relationships UNVERIFIED grey. Component nodes are structural, not health assertions. No synthetic packet animation. Safety/actuator permission is never inferred. Service failures can be inspected in the service-state history; a missing scrape is not asserted to be a failed component.

## Source verification — 2026-11-02
Read-only deployed source/configuration audit confirmed dashboard subscriptions for encoder health, board IMU heading, odometry, filtered scan, ultrasonic validity, joystick, control policy and camera-preview receipt metadata. The latter is not calibration CameraInfo or proof of individual image-frame delivery.
EKF configuration uses `/yahboom/odom` and `/im10a/imu/bias_corrected_candidate`; STM32 heading is not falsely presented as the EKF IMU input. Raw LiDAR is remapped to scan_raw; downstream filtering is not claimed verified. FlySky teleop and Nav2 were inactive at inspection.
Cached observation at 08:56:27 IST showed encoder health 10 Hz, odometry 9.99 Hz, LiDAR 1.83 Hz, ultrasonic validity 3.68 Hz, joystick 16.48 Hz, control policy 10.01 Hz and preview metadata 0.95 Hz. These historical cache measurements do not establish current end-to-end traffic. Structural connections lacking measured link evidence remain grey.

## Focused validation and limits
Four Python structural/generation tests and nine actual Prometheus promtool query simulations pass: fresh, idle, stale, ageing, scrape loss, missing rate, negative rate, unavailable topic and stale exporter collection. Health Monitor is unchanged. No new Jetson runtime overhead is introduced by repository preparation. Offline browser measurements are recorded below; live scrape/query overhead remains unmeasured.
Isolated Grafana browser validation PASSED (details below). Reboot and physical outage recovery remain PENDING; simulations are not physical reliability evidence. Windows startup task remains unregistered. PC-only dashboard import is GO for separate approval; this is not a reboot-reliability or live-traffic acceptance.

## Approval-gated rollout and rollback
Generate with `python monitoring/atlas/grafana/build_neural_dashboard.py`. Review/import only `dashboards/atlas-neural.json` into an isolated Grafana test instance before production approval. Verify nodes/edges frame conversion, colours under missing data, and history links. Production import requires separate approval. Rollback removes only UID `atlas-live-neural-data-flow` and its new provisioning file if one was installed; never remove or overwrite Health Monitor. No exporter, firewall, watchdog or robot-service changes are required.
Robot navigation, mapping and safety never depend on this visualization or Windows. Original watchdog cause remains UNKNOWN and fault latches must not be cleared automatically.

## Browser acceptance — 2026-11-02
PASS in isolated authenticated Grafana 12.1.0 (localhost:3301), existing image, no plugins. Edge Chromium headless at 1440x1000 and 390x844. No rover access in this browser-validation session.

- All 19 nodes and 20 edges rendered; eight audited observation paths and twelve explicitly unverified relationships.
- Controlled fixture queries passed through the real Grafana Prometheus datasource and existing local Prometheus query engine. Every browser datasource request, including popup history views, was intercepted with synthetic vector expressions. This validates real frame conversion and UI, not live traffic.
- Fresh/STALE/IDLE/UNAVAILABLE/UNVERIFIED edge colours and context labels checked; all 20 edge topic links checked. Actual node-to-Health and edge-to-topic-history popup navigation passed. Mobile node history click passed with menu inside viewport.
- Browser exposed duplicate menu links and mobile clipping. Links now belong only to the ID field; compact menu evidence labels refer to full topology notes below the graph. No query safety thresholds changed.
- 30-second automatic refresh observed across a 31-second window. No SVG packet animation. Unknown observations are grey, never green/zero.
- Four focused Python checks, nine promtool query simulations, browser acceptance and git whitespace check PASS. Health Monitor checkout SHA256 unchanged: 8337f6b2417d1abca579faa0d7935615d12295e5e9e5e9eda2ee00f9b97ed3ed.

Measured browser sample: graph present after 627 ms; renderer task time 0.426 s; JS heap 55.86 MiB. During the 31-second refresh window, renderer task time was 0.160 s. This is one cached local browser sample, not whole-PC CPU/RAM or Jetson overhead.

### Reproduce focused UI test
Use a disposable Grafana 12.1.0 container on localhost:3301 with authentication and no production volume mounts. Existing local Prometheus at :9090 receives synthetic vector queries only. Set ATLAS_BROWSER_LAB to a private temporary directory containing grafana.env with the disposable GF_SECURITY_ADMIN_PASSWORD. Provide existing Playwright through NODE_PATH, then run `node monitoring/atlas/grafana/browser_neural_check.cjs`. The test imports copies into the isolated instance only. It does not install plugins. Remove the disposable container and credentials afterward; never run against a production instance.

Remaining limitations: built-in layered graph needs pan/zoom (two zoom-out clicks give overview); parallel MCU receipt edges overlap, with exact topic diagnostics available via the topic selector/history. Mobile validation is viewport emulation, not physical-phone acceptance. Real production metrics/overhead and reboot recovery remain separately pending. No new live-health claim is made.
