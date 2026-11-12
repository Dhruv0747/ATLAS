#!/usr/bin/env bash
# Read-only side recording for offline colour 3D mapping (no commands published, no services touched).
#   domain 77: Astra colour + depth + camera_info + depth->colour extrinsic + static TF
#   domain 0 : /scan /odom /yahboom/odom /tf /tf_static /im10a/imu/bias_corrected_candidate
# Usage: color_side_record.sh LABEL   ; stop: touch /tmp/color_rec_stop (or 40 min cap). Pauses if disk < 20 GB.
set -u
LABEL=${1:-colour_map}; STAMP=$(date +%Y%m%d-%H%M%S)
OUT=$HOME/project_atlas/maps3d/${LABEL}_${STAMP}; mkdir -p "$OUT"; rm -f /tmp/color_rec_stop
set +u; source /opt/ros/humble/setup.bash; source /home/jetson/project-atlas-migration/astra-20261021/astra-arm64-stage29-v2/local_setup.bash; set -u   # driver msg types (Extrinsics)
ROS_DOMAIN_ID=77 setsid nice -n 5 ros2 bag record -o "$OUT/astra" \
  /astra/color/image_raw /astra/color/camera_info /astra/depth/image_raw /astra/depth/camera_info \
  /astra/extrinsic/depth_to_color /tf_static > "$OUT/astra.log" 2>&1 &
P1=$!
ROS_DOMAIN_ID=0 setsid nice -n 5 ros2 bag record -o "$OUT/base" \
  /scan /odom /yahboom/odom /tf /tf_static /im10a/imu/bias_corrected_candidate /amcl_pose /map > "$OUT/base.log" 2>&1 &
P2=$!
echo "$OUT" > /tmp/color_rec_path; echo "$P1 $P2" > /tmp/color_rec_pids
echo "recording to $OUT (pids $P1 $P2)"
T0=$(date +%s)
while [ ! -e /tmp/color_rec_stop ] && [ $(( $(date +%s) - T0 )) -lt 2400 ]; do
  FREE=$(df --output=avail -BG / | tail -1 | tr -dc 0-9); [ "$FREE" -lt 20 ] && { echo "disk low ${FREE}G, stopping"; break; }
  sleep 2
done
for p in $P1 $P2; do kill -INT -- -$p 2>/dev/null || kill -INT $p 2>/dev/null; done
sleep 6; for p in $P1 $P2; do kill -TERM -- -$p 2>/dev/null; done
du -sh "$OUT"/* 2>/dev/null; echo stopped
