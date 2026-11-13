#!/bin/bash
# OFFLINE (isolated ROS domain 92, localhost only): replay one drive bag through the ICP odometry node and several
# EKF variants derived from the live config/atlas_ekf.yaml, then score each by return-to-start closure (the
# operator drove back onto the start mark) and path length. Never touches the live graph. 2026-11-13.
# Usage: bash ekf_variants.sh BAG [RATE]   -> /tmp/ekf_variants_<bag>/{<variant>.csv, summary.json}
BAG=$1; RATE=${2:-1.0}; T=/tmp/ekf_variants_$(basename $BAG); rm -rf $T; mkdir -p $T
export ROS_DOMAIN_ID=92 ROS_LOCALHOST_ONLY=1
source /opt/ros/humble/setup.bash; source /home/jetson/project_atlas_ws/install/setup.bash 2>/dev/null
python3 - "$T" <<'PY'
import sys, copy, yaml, json
from pathlib import Path
T = Path(sys.argv[1]); live = yaml.safe_load(Path('/home/jetson/project_atlas/config/atlas_ekf.yaml').read_text())['atlas_ekf']['ros__parameters']
live['use_sim_time'] = True; live['publish_tf'] = False
VX = 6 * 15 + 6
def v(name, f):
    p = copy.deepcopy(live); f(p); return name, p
def drop_icp(p):
    for k in [k for k in p if k.startswith('odom1')]: del p[k]
def icp_only(p): p['odom0_config'] = [False] * 15
def qvx(val):
    def f(p): p['process_noise_covariance'][VX] = val
    return f
def icp_yaw(p): c = list(p['odom1_config']); c[11] = True; p['odom1_config'] = c
def icp_yaw_no_imu(p):
    icp_yaw(p); c = list(p['imu0_config']); c[11] = False; p['imu0_config'] = c
def icp_pose_diff(p):
    c = [False] * 15; c[0] = c[1] = c[5] = True; p['odom1_config'] = c; p['odom1_differential'] = True
    c = list(p['imu0_config']); c[11] = False; p['imu0_config'] = c
variants = dict([v('live', lambda p: None), v('wheel_imu_no_icp', drop_icp), v('icp_no_wheel', icp_only),
                 v('live_qvx_0.5', qvx(0.5)), v('live_qvx_8', qvx(8.0)), v('live_icp_yawrate', icp_yaw),
                 v('icp_yawrate_no_imu', icp_yaw_no_imu), v('icp_pose_diff_no_imu', icp_pose_diff)])
import os
keep = os.environ.get('VARIANTS')
if keep:
    variants = {k: p for k, p in variants.items() if k in keep.split(',')}
for n, p in variants.items():
    (T / f'{n}.yaml').write_text(yaml.safe_dump({f'ekf_{n.replace(".", "_")}': {'ros__parameters': p}}))
(T / 'variants.txt').write_text('\n'.join(variants))
(T / 'qos.yaml').write_text("/tf_static:\n  durability: transient_local\n  reliability: reliable\n  history: keep_all\n")
PY
PIDS=""
for n in $(cat $T/variants.txt); do
  setsid /opt/ros/humble/lib/robot_localization/ekf_node --ros-args -r __node:=ekf_${n//./_} --params-file $T/$n.yaml \
    -r odometry/filtered:=/test/${n//./_} > $T/$n.log 2>&1 & PIDS="$PIDS $!"
done
setsid python3 /home/jetson/project_atlas/scripts/atlas_icp_odometry.py --ros-args -p use_sim_time:=true > $T/icp.log 2>&1 & PIDS="$PIDS $!"
setsid python3 - "$T" > $T/rec.log 2>&1 <<'PY' &
import sys, math, rclpy
from nav_msgs.msg import Odometry
T = sys.argv[1]; rclpy.init()
n = rclpy.create_node('variant_rec', parameter_overrides=[rclpy.parameter.Parameter('use_sim_time', rclpy.Parameter.Type.BOOL, True)])
names = open(f'{T}/variants.txt').read().split() + ['icp_raw', 'wheel_raw']
out = {k: open(f'{T}/{k}.csv', 'w') for k in names}
def cb(k):
    def f(m):
        q = m.pose.pose.orientation; y = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
        out[k].write(f'{m.header.stamp.sec + m.header.stamp.nanosec*1e-9:.3f},{y:.5f},{m.pose.pose.position.x:.4f},{m.pose.pose.position.y:.4f}\n'); out[k].flush()
    return f
for k in names[:-2]:
    n.create_subscription(Odometry, '/test/' + k.replace('.', '_'), cb(k), 50)
n.create_subscription(Odometry, '/lidar/icp_odom', cb('icp_raw'), 50)
n.create_subscription(Odometry, '/yahboom/odom', cb('wheel_raw'), 50)
rclpy.spin(n)
PY
PIDS="$PIDS $!"
sleep 6
ros2 bag play $BAG --rate $RATE --topics /scan /tf_static /yahboom/odom /im10a/imu/bias_corrected_candidate --clock \
  --qos-profile-overrides-path $T/qos.yaml > $T/play.log 2>&1
sleep 3
for p in $PIDS; do kill -INT -- -$p 2>/dev/null; done; sleep 3; for p in $PIDS; do kill -KILL -- -$p 2>/dev/null; done
python3 - "$T" <<'PY'
import sys, json, math, numpy as np
from pathlib import Path
T = Path(sys.argv[1]); res = {}
w = np.loadtxt(T / 'wheel_raw.csv', delimiter=',', ndmin=2)
# drive window from wheel odometry: first/last sample with wheel displacement > 2 cm from its neighbours
step = np.r_[0, np.hypot(np.diff(w[:, 2]), np.diff(w[:, 3]))]
moving = np.nonzero(step > 0.002)[0]
t_start, t_end = (w[moving[0], 0] - 2.0, w[moving[-1], 0] + 2.0) if len(moving) else (w[0, 0], w[-1, 0])
for f in sorted(T.glob('*.csv')):
    a = np.loadtxt(f, delimiter=',', ndmin=2)
    if len(a) < 10: res[f.stem] = 'no output'; continue
    s = a[np.searchsorted(a[:, 0], t_start).clip(0, len(a) - 1)]; e = a[np.searchsorted(a[:, 0], t_end).clip(0, len(a) - 1)]
    seg = a[(a[:, 0] >= t_start) & (a[:, 0] <= t_end)]
    path = float(np.hypot(np.diff(seg[:, 2]), np.diff(seg[:, 3])).sum()) if len(seg) > 1 else 0.0
    dyaw = math.degrees(math.atan2(math.sin(e[1] - s[1]), math.cos(e[1] - s[1])))
    res[f.stem] = {'closure_m': round(float(math.hypot(e[2] - s[2], e[3] - s[3])), 3), 'closure_yaw_deg': round(dyaw, 1),
                   'path_m': round(path, 2), 'samples': len(a)}
res['_window'] = {'start': t_start, 'end': t_end, 'drive_s': round(t_end - t_start, 1)}
(T / 'summary.json').write_text(json.dumps(res, indent=1)); print(json.dumps(res, indent=1))
PY
