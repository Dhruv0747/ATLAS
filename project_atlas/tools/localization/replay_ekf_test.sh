#!/bin/bash
# OFFLINE test (isolated ROS domain 92, localhost only): replay a recorded drive's wheel odometry + IM10A gyro through
# two robot_localization EKFs side by side - CURRENT live config and CANDIDATE (wheel velocities only, no wheel x/y)
# - and record both headings. Never touches the live rover graph. Usage: bash replay_ekf_test.sh BAG [RATE]
BAG=$1; RATE=${2:-2.0}; T=/tmp/ekf_replay_$$; mkdir -p $T
export ROS_DOMAIN_ID=92 ROS_LOCALHOST_ONLY=1
source /opt/ros/humble/setup.bash
python3 - "$T" <<'PY'
import sys, yaml
from pathlib import Path
T = Path(sys.argv[1]); base = yaml.safe_load(Path('/home/jetson/project_atlas/config/atlas_ekf.yaml').read_text())['atlas_ekf']['ros__parameters']
for name, cfg in (('current', None), ('candidate', [False, False, False, False, False, False, True, True, False, False, False, False, False, False, False])):
    p = dict(base); p['use_sim_time'] = True; p['publish_tf'] = False
    if cfg: p['odom0_config'] = cfg
    (T / f'{name}.yaml').write_text(yaml.safe_dump({f'ekf_{name}': {'ros__parameters': p}}))
print('configs written')
PY
for n in current candidate; do
  setsid /opt/ros/humble/lib/robot_localization/ekf_node --ros-args -r __node:=ekf_$n --params-file $T/$n.yaml -r odometry/filtered:=/test/$n > $T/$n.log 2>&1 &
  echo $! >> $T/pgids
done
python3 - "$T" > $T/rec.log 2>&1 <<'PY' &
import sys, math, rclpy, json
from nav_msgs.msg import Odometry
T = sys.argv[1]; rclpy.init(); n = rclpy.create_node('replay_rec', parameter_overrides=[rclpy.parameter.Parameter('use_sim_time', rclpy.Parameter.Type.BOOL, True)])
out = {k: open(f'{T}/{k}.csv', 'w') for k in ('current', 'candidate')}
def cb(k):
    def f(m):
        q = m.pose.pose.orientation; y = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
        out[k].write(f'{m.header.stamp.sec + m.header.stamp.nanosec*1e-9:.3f},{y:.5f},{m.pose.pose.position.x:.3f},{m.pose.pose.position.y:.3f}\n'); out[k].flush()
    return f
for k in out: n.create_subscription(Odometry, f'/test/{k}', cb(k), 50)
rclpy.spin(n)
PY
REC=$!; echo $REC >> $T/pgids
sleep 4
ros2 bag play $BAG --topics /yahboom/odom /im10a/imu/bias_corrected_candidate --clock --rate $RATE > $T/play.log 2>&1
sleep 3
for p in $(cat $T/pgids); do kill -INT $p 2>/dev/null; done; sleep 2; for p in $(cat $T/pgids); do kill -KILL $p 2>/dev/null; done
echo "outputs: $(wc -l < $T/current.csv) current, $(wc -l < $T/candidate.csv) candidate rows in $T"
echo $T > /tmp/ekf_replay_last
