#!/usr/bin/env bash
# Offline native robot_localization EKF replay of ONE recorded drive, for a config variant.
# Runs only on an isolated machine (PC/cloud workspace), never on the rover. Inputs: the bag's own
# /yahboom/odom, /im10a/imu/bias_corrected_candidate and /tf_static, unmodified, with /clock from bag
# receipt time. Output: CSV of the native /odom (sim receipt time, header stamp, x, y, yaw, cov xx, yy).
#   ekf_ab_replay.sh <params.yaml> <bag_dir> <out.csv> [rate]
set -eo pipefail
PARAMS=$(realpath "$1"); BAG=$(realpath "$2"); OUT=$(realpath -m "$3"); RATE=${4:-4}
export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-91}   # private domain; the workspace has no robot on its network
PY=/usr/bin/python3.12   # ROS Jazzy binaries are built for 3.12
source /opt/ros/${ROS_DISTRO_NAME:-jazzy}/setup.bash
# `ros2 run` leaves its child alive when the wrapper is killed, so the binary is started directly and
# a run refuses to start while any other EKF replay exists (a second /odom publisher would mix results).
pgrep -f "robot_localization/ekf_node" >/dev/null && { echo "refusing: another ekf_node is running"; exit 2; }
PIDS=(); trap 'for p in "${PIDS[@]}"; do kill $p 2>/dev/null; done; sleep 1; for p in "${PIDS[@]}"; do kill -9 $p 2>/dev/null; done' EXIT
/opt/ros/${ROS_DISTRO_NAME:-jazzy}/lib/robot_localization/ekf_node --ros-args -r __node:=atlas_ekf --params-file "$PARAMS" -r odometry/filtered:=/odom -p use_sim_time:=true > "$OUT.ekf.log" 2>&1 & PIDS+=($!)
/usr/bin/python3.12 - "$OUT" > "$OUT.logger.log" 2>&1 <<'PY' & PIDS+=($!)
import math, sys, rclpy
from nav_msgs.msg import Odometry
from rclpy.parameter import Parameter
rclpy.init(); n = rclpy.create_node('ab_logger', parameter_overrides=[Parameter('use_sim_time', value=True)])
f = open(sys.argv[1], 'w'); f.write('t,stamp,x,y,yaw,cxx,cyy\n')
def cb(m):
    q = m.pose.pose.orientation; yaw = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
    t = n.get_clock().now().nanoseconds*1e-9; s = m.header.stamp.sec + m.header.stamp.nanosec*1e-9
    f.write(f'{t:.6f},{s:.6f},{m.pose.pose.position.x:.6f},{m.pose.pose.position.y:.6f},{yaw:.6f},{m.pose.covariance[0]:.6g},{m.pose.covariance[7]:.6g}\n'); f.flush()
n.create_subscription(Odometry, '/odom', cb, 50); rclpy.spin(n)
PY
sleep 3
/usr/bin/python3.12 /opt/ros/jazzy/bin/ros2 bag play "$BAG" --clock 200 --rate "$RATE" --topics /yahboom/odom /im10a/imu/bias_corrected_candidate /tf_static > "$OUT.play.log" 2>&1
sleep 2
N=$(pgrep -fc "robot_localization/ekf_node" || true); [ "$N" = 1 ] || { echo "invalid run: $N ekf_node processes"; exit 3; }
wc -l < "$OUT"
