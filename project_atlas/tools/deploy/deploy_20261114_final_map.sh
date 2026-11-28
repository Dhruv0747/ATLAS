#!/bin/bash
# Deploy the 2026-11-14 final-map acceptance check (owner OK 2026-11-14) and switch it ON.
# Run ON THE JETSON with the rover parked and motion stopped. Restarts ONLY atlas-mission-control (no odom/LiDAR/Nav2).
# Backups: <file>.before-finalmap-20261114 ; rollback: bash $0 --rollback
set -euo pipefail
S=~/atlas_staging_20261113; L=~/project_atlas; TAG=before-finalmap-20261114
D=~/.config/systemd/user/atlas-mission-control.service.d; DROPIN=$D/final-map-mode.conf
FILES="atlas_mission_control.py atlas_map_acceptance_core.py atlas_final_map_consistency.py"
TESTS="test_final_map_consistency.py test_mission_final_map_sampling.py test_atlas_map_acceptance_core.py"
if [ -f ~/.config/project_atlas/mapping_session.json ]; then echo "mapping session open - refusing"; exit 1; fi
if [ "${1:-}" = "--rollback" ]; then
  for f in $FILES; do
    if [ -f $L/scripts/$f.$TAG ]; then cp -p $L/scripts/$f.$TAG $L/scripts/$f
    elif [ -f $L/scripts/$f.$TAG.new ]; then rm -f $L/scripts/$f $L/scripts/$f.$TAG.new; fi
  done
  rm -f $DROPIN
else
  for f in $FILES; do
    if [ -f $L/scripts/$f ]; then cp -p $L/scripts/$f $L/scripts/$f.$TAG; else touch $L/scripts/$f.$TAG.new; fi
    cp $S/scripts/$f $L/scripts/$f
  done
  for t in $TESTS; do cp $S/tests/$t $L/tests/$t; done
  mkdir -p $D
  cat > $DROPIN <<'UNIT'
[Service]
ExecStart=
ExecStart=/bin/bash -lc 'source /opt/ros/humble/setup.bash; source /home/jetson/project_atlas_ws/install/setup.bash; exec /usr/bin/python3 /home/jetson/project_atlas/scripts/atlas_mission_control.py --ros-args -p map_acceptance_slam_tf_future_offset_s:=1.5 -p map_acceptance_final_map_mode:=true'
UNIT
fi
systemctl --user daemon-reload
systemctl --user restart atlas-mission-control.service
sleep 12
systemctl --user is-active atlas-mission-control.service
