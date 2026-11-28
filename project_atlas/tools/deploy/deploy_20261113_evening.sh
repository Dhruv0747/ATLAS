#!/bin/bash
# Deploy the 2026-11-13 evening staged changes (light mapping mode, mapping guard, batched monitors, dashboard backlog).
# Run ON THE JETSON only with the owner present, rover parked, E-STOP latched. No motion is commanded.
# Every replaced file is backed up as <file>.before-evening-20261113; rollback: bash $0 --rollback
set -euo pipefail
S=~/atlas_staging_20261113; L=~/project_atlas; U=~/.config/systemd/user; TAG=before-evening-20261113
FILES="atlas_mission_control.py atlas_cmd_vel_mux.py atlas_feature_on_demand.py atlas_sensor_recovery.py atlas_safety_status.py
       atlas_lidar_odom_gate.py atlas_localization_monitor.py atlas_status_web.py record_atlas_demonstration.sh
       atlas_batched_spin.py atlas_mapping_guard_core.py"
UNITS="atlas-localization-monitor atlas-sensor-recovery atlas-mission-control atlas-safety-status atlas-lidar-odom-gate"
RESTART="atlas-mission-control atlas-cmd-vel-mux atlas-feature-on-demand atlas-sensor-recovery atlas-safety-status
         atlas-localization-monitor atlas-lidar-odom-gate rover-status-web"
if [ "${1:-}" = "--rollback" ]; then
  for f in $FILES; do
    if [ -f $L/scripts/$f.$TAG ]; then cp -p $L/scripts/$f.$TAG $L/scripts/$f
    elif [ -f $L/scripts/$f.$TAG.new ]; then rm -f $L/scripts/$f; fi
  done
  for u in $UNITS; do rm -f $U/$u.service.d/batched-executor.conf; done
else
  [ -f $S/scripts/atlas_mapping_guard_core.py ] || { echo "staging missing"; exit 1; }
  for f in $FILES; do
    if [ -f $L/scripts/$f ]; then cp -p $L/scripts/$f $L/scripts/$f.$TAG; else touch $L/scripts/$f.$TAG.new; fi
    cp $S/scripts/$f $L/scripts/$f
  done
  for u in $UNITS; do mkdir -p $U/$u.service.d; cp $S/systemd/user/$u.service.d/batched-executor.conf $U/$u.service.d/; done
  cp $S/tests/regression_known_failures.txt $L/tests/ 2>/dev/null || true
fi
systemctl --user daemon-reload
for u in $RESTART; do echo "restart $u"; systemctl --user restart $u.service; sleep 2; done
sleep 10
systemctl --user is-active $(for u in $RESTART; do echo $u.service; done) | paste -sd' '
