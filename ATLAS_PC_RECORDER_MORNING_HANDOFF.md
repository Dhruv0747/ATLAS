# PC recorder checkpoint — 14 October 2026

Work paused at owner's request. No overnight testing or automation.

## Completed

PC-only installation: WSL3.0.3, WSL2 Ubuntu22.04.5, ROS2 Humble ros-base,
rosbag2 0.15.17, rclpy3.3.22, FastDDS2.6.12, demo nodes, nav2 message schemas.
No Windows reboot; pre-existing VirtualMachinePlatform preserved; legacy WSL1
feature stays disabled. No manual firewall changes or production ROS connections.

Native isolated test:30.0061sec,1454 sent/received, zero missing sequences,
SQLite integrity and native rosbag payload/recording-timestamp roundtrip passed.
Two nodes in one process; separate network namespace, domain187, localhost-only.
CPU15.781% of ONE core; peak process RSS58.93MiB; bag94881 bytes.
This is a small Int32 smoke test, not full ATLAS topic coverage or network validation.
Int32 has no source Header; source clock accuracy was not established.

The initial passing test used /tmp, whose evidence disappeared after WSL exited.
Final repeat writes persistent Linux storage and copies evidence to Windows before
exit. Both outcomes are preserved in the local result narrative.

## Preserved locally (not uploaded to Git)

Windows workspace root: `C:/Users/Dhruv/Documents/Codex/2026-07-24/h`.
Evidence folder: `atlas_wsl_install_evidence/` contains installation transcript,
`PLAN_AND_ROLLBACK.txt`, `RESULT.txt`, and `native-2kvn9odm/` result plus bag.
Linux evidence: `/root/atlas_pc_diagnostics/native-2kvn9odm`.
Windows UAC installation script: `atlas_wsl_prepare.ps1` in workspace root.
Generated ROS output, logs and unrelated historical artifacts are deliberately
kept local per repository policy; nothing was deleted or reset.

Source copies: `project_atlas/tools/diagnostics/atlas_pc_ros_setup.sh`,
`atlas_pc_ros_smoke.sh`, `atlas_pc_ros_smoke.py`. These retain the actual approved
workspace paths and are not portable installers. Do not rerun completed setup/tests
merely to resume. No background service or autostart was installed.

## Morning next step

1. Reuse installed PC runtime; do not repeat installation or localization audits.
2. Complete isolated full-topic/schema/QoS/source-timestamp tests.
3. Qualify clock offset and select bounded private transport; preserve existing
   Wi-Fi → cellular → hotspot policy. No network/firewall modifications yet approved.
4. Request separate approval before any stationary live Jetson subscription/capture.
   Measure before/during/after Jetson CPU/network/freshness using existing safeguards.
5. Moving tests require further explicit approval. Private EKF/AMCL state gaps remain.

No Jetson service, steering, map, safety limit or fusion changes were made. No
E-STOP release or autonomous movement issued. Installed Stage20 recorder was left
OFF; its live state must be freshly checked before any future approved activity.
No Jetson CPU saving or navigation reliability improvement is claimed from PC tests.

Rollback: preserve/export Ubuntu evidence before explicit distribution removal;
unregistering deletes Linux data. Remove only newly installed components if approved.
Never disable pre-existing VirtualMachinePlatform or alter unrelated applications.
