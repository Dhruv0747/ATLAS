# Daly BMS freshness repair — 2026-10-09

## Observed failure

Stopped-runtime journal from 09:51–09:58 IST alternated complete four-cell snapshots near 13.1–13.2 V / 87.8–89.5% with repeated 8-second `connect` deadlines. The service stayed active with zero reported restarts in that window. This does **not** establish the cause of the BLE connection failures: phone contention, radio conditions, Bluetooth stack state and repeated connection setup remain competing possibilities. No radio reset or BMS hardware change was made.

Source inspection found a separate concrete freshness defect: `daly_bms_node.py` marked the JSON payload `ok:false` on failure, but `publish_data` also republished scalar SOC/voltage/current/cell values copied from `self.last`. Scalar topics carry no `ok` or measurement timestamp. The agent supervisor used `/bms/percent` and therefore refreshed its SOC age on the copied value, potentially allowing its battery preflight until its separate timeout elapsed.

## Bounded source repair

- Always publish JSON status; publish scalar values only for a complete `ok:true` snapshot. Failed reads can no longer masquerade as new scalar measurements.
- Make the agent supervisor consume coherent `/bms/json` instead of scalar SOC. Invalid, incomplete or malformed snapshots immediately clear its SOC and age; its existing preflight therefore fails closed. Motion safety limits and motor control are unchanged.
- Add non-ROS tests for a healthy→failed sequence and malformed/nonfinite agent snapshots.

## Validation and deployment boundary

The 14 relevant offline Daly tests pass; both changed Python modules compile. This is **source-level validation only**. The live BMS and agent services have not been restarted or changed. After an authorized deployment, confirm that `ok:false` continues on JSON, scalar age grows instead of resetting, the agent denies motion while invalid, recovery restores fresh values, and the BLE connection failure rate is measured separately. Rollback is the pre-change repository revision and service files; do not roll back without preserving the stale-data safety finding.

The 5-second ROS timer can be overdue after an 8-second blocking BLE timeout, and journal bursts of sub-second successful polls were observed. Timer catch-up is a hypothesis for extra connection churn, **not** a proven cause of connect failures; do not change polling cadence without a separate A/B test and battery-safety review.
