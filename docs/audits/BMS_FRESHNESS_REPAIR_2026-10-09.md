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

If rollback is necessary, stop only the two affected user services, restore each matching `.before` file with mode 755 and restart them. This would reintroduce the known stale-scalar defect, so use it only if the new build causes a worse verified fault and keep motion inhibited until freshness is restored.

The 5-second ROS timer can be overdue after an 8-second blocking BLE timeout, and journal bursts of sub-second successful polls were observed. Timer catch-up is a hypothesis for extra connection churn, **not** a proven cause of connect failures; do not change polling cadence without a separate A/B test and battery-safety review.
