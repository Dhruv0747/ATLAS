# Daly BMS freshness repair — 2026-10-09

## Observed failure

Stopped-runtime journal from 09:51–09:58 IST alternated complete four-cell snapshots near 13.1–13.2 V / 87.8–89.5% with repeated 8-second `connect` deadlines. The service stayed active with zero reported restarts in that window. This does **not** establish the cause of the BLE connection failures: phone contention, radio conditions, Bluetooth stack state and repeated connection setup remain competing possibilities. No radio reset or BMS hardware change was made.

Source inspection found a separate concrete freshness defect: `daly_bms_node.py` marked the JSON payload `ok:false` on failure, but `publish_data` also republished scalar SOC/voltage/current/cell values copied from `self.last`. Scalar topics carry no `ok` or measurement timestamp. The agent supervisor used `/bms/percent` and therefore refreshed its SOC age on the copied value, potentially allowing its battery preflight until its separate timeout elapsed.

## Bounded source repair

- Always publish JSON status; publish scalar values only for a complete `ok:true` snapshot. Failed reads can no longer masquerade as new scalar measurements.
- Make the agent supervisor consume coherent `/bms/json` instead of scalar SOC. Invalid, incomplete or malformed snapshots immediately clear its SOC and age; its existing preflight therefore fails closed. Motion safety limits and motor control are unchanged.
- Add non-ROS tests for a healthy→failed sequence and malformed/nonfinite agent snapshots.

## Validation and deployment boundary

The 14 relevant offline Daly tests and 12 agent-core tests pass; both changed Python modules compile. Commit `5bdce11` was pushed to the active GitHub branch. With explicit operator approval and the rover stopped, only the BMS and mission-agent scripts were installed and those two services restarted at about 10:04:55 IST. The previous files are preserved at `/home/jetson/project_atlas/data/deploy_backups/20261009_bms_freshness/*.before`. Source SHA-256 on Jetson: `daly_bms_node.py` = `31b9cf3f86166206bf3a119dd2496a70929d72c91f1ce977c3d04a7a8bf355bb`; `atlas_agent_supervisor.py` = `e1607944f945564770e7649897c8817d526b1188300a3abdf6eb05c7bd49a5c8`.

The BMS and agent restarted active, each with zero post-restart systemd restart count. The motor owner kept PID 3120 and NRestarts=0. The first ~75 seconds of BMS logs showed complete healthy snapshots near 13.1–13.2 V / 86.0–86.3% and no observed connect failure. A 20-second API sample showed BMS JSON, scalar SOC and agent SOC ages advancing normally on healthy reads. This is a **short healthy-runtime pass only**; the invalid→scalar-age/agent-inhibit behavior was not exercised live because no natural failure occurred in the observation window. Do not intentionally disconnect the BMS merely to manufacture a pass. A 10-minute stopped endurance observation and eventual natural-failure/recovery comparison are still required before calling the BLE problem fixed.

At 10:07:12 IST the new BMS process logged another `Daly Bluetooth response deadline exceeded during connect`; the service remained active and subsequently published complete readings. Thus the BLE connection fault is demonstrably **not fixed** by the freshness repair. Forty later one-second dashboard samples did not coincide with an invalid JSON sample, so the new scalar-age and agent-inhibit behavior on a live failed read remains unobserved. Offline regressions cover that contract, but a live pass must not be claimed from the missed sampling window.

Read-only Bluetooth journal around that failure showed multiple connect/disconnect cycles for the same BMS address and `bonding_attempt_complete ... status 0x0e` lines. The current transport launches a new interactive `gatttool` process for each poll, so repeated setup is a plausible contributor. The BlueZ status/reason codes have **not** been independently decoded here and do not prove phone contention, radio failure or BMS hardware failure. A persistent-connection or pacing change requires a separate bounded comparison, not an unmeasured timeout increase.

If rollback is necessary, stop only the two affected user services, restore each matching `.before` file with mode 755 and restart them. This would reintroduce the known stale-scalar defect, so use it only if the new build causes a worse verified fault and keep motion inhibited until freshness is restored.

The 5-second ROS timer can be overdue after an 8-second blocking BLE timeout, and journal bursts of sub-second successful polls were observed. Timer catch-up is a hypothesis for extra connection churn, **not** a proven cause of connect failures; do not change polling cadence without a separate A/B test and battery-safety review.

The consolidated dashboard's health grid previously classified any recent `/bms/status` message as healthy, even when its JSON said `ok:false`. Its main power card also displayed a last-known scalar percentage unconditionally. A first source repair required valid JSON and fresh scalar SOC. A later web-only deployment replaced that split check with one complete `/bms/status` packet no older than 10 seconds, showing net current/power and hiding all last-known values when invalid. The web assets were backed up as `*.bak-20261009-bms-ui`; only `rover-status-web.service` restarted. The BMS reader and motor services did not restart for this UI change. HTTP 200 and a fresh 4-cell packet were observed afterward; this does not repair the BLE transport.

At 10:14:25 IST, the stopped-runtime journal since 10:05 contained 112 complete BMS snapshots and one connect timeout; both restarted services remained active with zero systemd restarts, and the motor base was still PID 3120 with zero restarts. This is not a pass for a no-failure BLE endurance criterion, nor did it capture the short invalid→agent-inhibit transition live.

At 10:15:05 IST, just over ten minutes after deployment, the same window contained 120 complete snapshots and **two** read failures. Service uptime held, but the proposed no-failure BLE endurance gate failed. Do not describe this as a Bluetooth-link repair or authorize motion from these data.

A later read-only journal check from 10:30 through about 11:15 IST found three additional `Daly Bluetooth response deadline exceeded during connect` warnings among successful polls. At 11:14 the web API again received a complete `ok:true` snapshot (13.1 V, -1.8 A, -23.58 W, 71.4% SOC, all four cells). This demonstrates recovery between failures, not a stable BLE link; no 10-minute no-failure gate can be claimed.
