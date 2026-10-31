# ATLAS handover — 2026-10-31 (next: standalone 3D mapping)

## Closed today
- **Monitoring:** PR #13 merged (`1165b69`). The Jetson exporter is live, Prometheus and Grafana run on the PC, and the dashboard is verified. Developer guide: PR #16 (docs, unmerged).
- **Superpowers:** PR #18 merged into `main` (`e488509`). Six skills plus `atlas-workflow` are in `.claude/skills`, with Codex manifests in `.agents/skills`.

## Still open
- **PR #15:** targets the `agent/stage28-base-maintenance-20261027` branch and carries the Stage 29 stop-analyzer fix. Not merged.
- **PR #16:** monitoring developer guide. Not merged.
- **Issue #17:** the original watchdog fault cause is UNKNOWN; reboot recovery of monitoring and Windows auto-start of Prometheus/Grafana are unverified.
- **Other items:** the CPU startup spike cause is UNKNOWN; AMCL live verification is pending; Recovery service fault response has not been fully verified.

## Facts measured on 2026-10-31 at 17:31 (read-only; re-measure before acting)
- RTAB-Map is **not installed**. There is no standard Astra/OpenNI/Orbbec ROS package; the Astra camera runs through custom ATLAS code.
- CPU is **51 % at idle** (61–63 % at times today) against a **75 % hard limit**. RAM: 3.0 of 7.6 GB free. Disk: 363 GB free.
- Heaviest processes: `camera_node` about 35 %, plus several python nodes at 18–45 %.
- **Main risk:** RTAB-Map with Astra RGB-D needs more than the 12–24 % of CPU left. Make CPU headroom first; never relax the 75 % / 80 % / 70 °C limits.

## Plan: one milestone at a time; each needs its actual PASS before the next
| # | Milestone | PASS means |
|---|---|---|
| M1 | **Mapping CPU budget:** read-only measurement, then decide what can stop or slow during mapping (e.g. `camera_node`, the pan-tilt stream) | Astra running in mapping mode at about 45 % CPU or less, with all safety services still up |
| M2 | Astra calibration and RGB-D alignment | Measured reprojection error; depth lines up with RGB |
| M3 | Install RTAB-Map (owner approval); map with the rover stationary, Astra only | A map is built on the Jetson within the CPU limit |
| M4 | Map a room by **manual** slow driving (FlySky/Xbox); save the map on the Jetson | `.db` map saved; works with the PC off |
| M5 | Lightweight 3D map view in the Glass UI dashboard | Map visible on the dashboard |
| M6 | Localization mode, then autonomous exploration | Separate approval, only after AMCL is verified live |

**Open question for the owner (blocks M1):** can the IMX708 `camera_node` and the pan-tilt stream be stopped or slowed while mapping?

## Rules that still apply
- No deploy, service restart, E-STOP release, motor command or firmware change without the owner's explicit approval for that action.
- Additive changes with backups.
- Risk-based testing.
- Offline evidence is never reported as physical PASS.
