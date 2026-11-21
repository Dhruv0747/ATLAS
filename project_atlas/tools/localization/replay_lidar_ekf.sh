#!/bin/bash
# OFFLINE (isolated ROS domain 93, localhost only): replay a drive bag through rf2o -> atlas_lidar_odom_gate ->
# LiDAR-assisted candidate EKF, plus the live EKF config, and record both outputs. Never touches the live graph.
# Usage: bash replay_lidar_ekf.sh BAG   -> writes $T/{current,lidar}.csv (stamp,yaw,x,y); $T in /tmp/lidar_replay_last
BAG=$1; T=/tmp/lidar_replay_$$; mkdir -p $T; echo $T > /tmp/lidar_replay_last
export ROS_DOMAIN_ID=93 ROS_LOCALHOST_ONLY=1
source /opt/ros/humble/setup.bash; source /home/jetson/project_atlas_ws/install/setup.bash
C=/home/jetson/project_atlas/config
python3 - "$T" <<'PY'
import sys, yaml
from pathlib import Path
T = Path(sys.argv[1]); C = Path('/home/jetson/project_atlas/config')
for name, src, key in (('current', 'atlas_ekf.yaml', 'atlas_ekf'), ('lidar', 'atlas_ekf_lidar_candidate.yaml', 'atlas_ekf_lidar_candidate')):
    p = yaml.safe_load((C / src).read_text())[key]['ros__parameters']; p['use_sim_time'] = True; p['publish_tf'] = False
    (T / f'{name}.yaml').write_text(yaml.safe_dump({f'ekf_{name}': {'ros__parameters': p}}))
(T / 'qos.yaml').write_text("/tf_static:\n  durability: transient_local\n  reliability: reliable\n  history: keep_all\n")
PY
PIDS=""
setsid /opt/ros/humble/lib/robot_localization/ekf_node --ros-args -r __node:=ekf_current --params-file $T/current.yaml -r odometry/filtered:=/test/current > $T/current.log 2>&1 & PIDS="$PIDS $!"
setsid /opt/ros/humble/lib/robot_localization/ekf_node --ros-args -r __node:=ekf_lidar --params-file $T/lidar.yaml -r odometry/filtered:=/test/lidar > $T/lidar.log 2>&1 & PIDS="$PIDS $!"
setsid /home/jetson/project_atlas_ws/install/rf2o_laser_odometry/lib/rf2o_laser_odometry/rf2o_laser_odometry_node --ros-args \
  --params-file $C/atlas_lidar_odom.yaml -p use_sim_time:=true > $T/rf2o.log 2>&1 & PIDS="$PIDS $!"
setsid python3 /home/jetson/project_atlas/scripts/atlas_lidar_odom_gate.py --ros-args -p use_sim_time:=true > $T/gate.log 2>&1 & PIDS="$PIDS $!"
setsid python3 - "$T" > $T/rec.log 2>&1 <<'PY' &
import sys, math, rclpy
from nav_msgs.msg import Odometry
T = sys.argv[1]; rclpy.init()
n = rclpy.create_node('replay_rec', parameter_overrides=[rclpy.parameter.Parameter('use_sim_time', rclpy.Parameter.Type.BOOL, True)])
out = {k: open(f'{T}/{k}.csv', 'w') for k in ('current', 'lidar', 'rf2o')}
def cb(k):
    def f(m):
        q = m.pose.pose.orientation; y = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
        out[k].write(f'{m.header.stamp.sec + m.header.stamp.nanosec*1e-9:.3f},{y:.5f},{m.pose.pose.position.x:.3f},{m.pose.pose.position.y:.3f}\n'); out[k].flush()
    return f
n.create_subscription(Odometry, '/test/current', cb('current'), 50)
n.create_subscription(Odometry, '/test/lidar', cb('lidar'), 50)
n.create_subscription(Odometry, '/lidar/odom', cb('rf2o'), 50)
rclpy.spin(n)
PY
PIDS="$PIDS $!"
sleep 5
ros2 bag play $BAG --topics /scan /tf_static /yahboom/odom /im10a/imu/bias_corrected_candidate --clock \
  --qos-profile-overrides-path $T/qos.yaml > $T/play.log 2>&1
sleep 3
for p in $PIDS; do kill -INT -- -$p 2>/dev/null; done; sleep 3; for p in $PIDS; do kill -KILL -- -$p 2>/dev/null; done
echo "rows: $(wc -l < $T/current.csv) current, $(wc -l < $T/lidar.csv) lidar, $(wc -l < $T/rf2o.csv) rf2o-gated; gate log:"; tail -2 $T/gate.log; tail -2 $T/rf2o.log
