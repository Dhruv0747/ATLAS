#!/bin/bash
# OFFLINE 2D map build (isolated ROS domain 93, localhost only; the live rover is not touched).
# Plays recorded drives (/scan, corrected EKF odom TF) through slam_toolbox (sync, offline params) and saves
# ~/project_atlas/maps/<NAME>.{yaml,pgm}. AMCL's old map->odom is DROPPED from the recorded /tf so the new map does not
# inherit the old map's errors. The active map is NOT changed. Usage: bash build_2d_map_offline.sh NAME BAG [BAG...]
NAME=$1; shift; T=/tmp/map2d_$$; mkdir -p $T
export ROS_DOMAIN_ID=93 ROS_LOCALHOST_ONLY=1
source /opt/ros/humble/setup.bash
P=$(ros2 pkg prefix slam_toolbox)/share/slam_toolbox/config/mapper_params_offline.yaml
python3 - "$P" "$T/params.yaml" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1])); p = d[list(d)[0]]['ros__parameters']
p.update(use_sim_time=True, odom_frame='odom', map_frame='map', base_frame='base_footprint', scan_topic='/scan', mode='mapping',
         resolution=0.05, max_laser_range=8.0, minimum_travel_distance=0.2, minimum_travel_heading=0.15, do_loop_closing=True,
         transform_publish_period=0.05)
yaml.safe_dump({'slam_toolbox': {'ros__parameters': p}}, open(sys.argv[2], 'w')); print('params ready')
PY
setsid ros2 run slam_toolbox sync_slam_toolbox_node --ros-args --params-file $T/params.yaml > $T/slam.log 2>&1 & echo $! >> $T/pids
# relay: recorded /tf minus anything parented by "map" (AMCL), republished as /tf
setsid python3 - > $T/relay.log 2>&1 <<'PY' & 
import rclpy
from tf2_msgs.msg import TFMessage
from rclpy.qos import QoSProfile
rclpy.init(); n = rclpy.create_node('tf_relay_no_map', parameter_overrides=[rclpy.parameter.Parameter('use_sim_time', rclpy.Parameter.Type.BOOL, True)])
pub = n.create_publisher(TFMessage, '/tf', 100)
def cb(m):
    keep = [t for t in m.transforms if t.header.frame_id != 'map']
    if keep: pub.publish(TFMessage(transforms=keep))
n.create_subscription(TFMessage, '/tf_rec', cb, 100); rclpy.spin(n)
PY
echo $! >> $T/pids
sleep 5
for B in "$@"; do
  echo "playing $(basename $B)"
  ros2 bag play $B --topics /scan /tf /tf_static --remap /tf:=/tf_rec --clock --rate 2.0 > $T/play_$(basename $B).log 2>&1
  sleep 2
done
sleep 4
ros2 run nav2_map_server map_saver_cli -f $HOME/project_atlas/maps/$NAME --ros-args -p use_sim_time:=true > $T/save.log 2>&1
tail -2 $T/save.log
grep -ciE "error" $T/slam.log | sed 's/^/slam_toolbox error lines: /'
for p in $(cat $T/pids); do kill -INT -- -$p 2>/dev/null; done; sleep 2; for p in $(cat $T/pids); do kill -KILL -- -$p 2>/dev/null; done
ls -la $HOME/project_atlas/maps/$NAME.* 2>/dev/null | awk '{print $5, $9}'
echo "leftover: $(ps -eo args | grep -cE '[s]ync_slam_toolbox|[t]f_relay_no_map')"
