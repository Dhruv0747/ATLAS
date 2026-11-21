#!/bin/bash
# Parked review of the remap-13 candidate: localize on a COPY of it, ask Nav2 for plans both ways (no goal sent),
# record footprint, then restore normal localization on the accepted map. No motion is commanded.
source /opt/ros/humble/setup.bash; source ~/project_atlas_ws/install/setup.bash
M=~/project_atlas/maps; C=$M/.atlas_candidate_21ed0671944a43f8840c7e72c048823f; R=$M/review_remap13; OUT=/tmp/review_remap13.json
cp $C.pgm $R.pgm; sed "s#^image:.*#image: review_remap13.pgm#" $C.yaml > $R.yaml
restore() {
  echo "restore: stopping review stack"
  if [ -n "$LPID" ]; then
    kill -INT -- -$LPID 2>/dev/null
    for i in $(seq 1 20); do sleep 1; pgrep -g $LPID >/dev/null || break; done
    pgrep -g $LPID >/dev/null && { echo "restore: forcing review group"; kill -9 -- -$LPID 2>/dev/null; sleep 2; }
  fi
  echo "restore: review processes left: $(pgrep -g ${LPID:-0} | wc -l)"
  systemctl --user start atlas-localization
  for i in $(seq 1 24); do sleep 5; timeout 3 ros2 lifecycle get /amcl 2>/dev/null | grep -q active && break; done
  python3 ~/project_atlas/scripts/seed_atlas_localization.py --verify-place "dhruv room" >/dev/null 2>&1 || true
  echo "restore: localization $(systemctl --user is-active atlas-localization)"
}
trap restore EXIT
systemctl --user stop atlas-nav2 atlas-localization
sleep 3
setsid ros2 launch tortoisebot_bringup atlas_localization.launch.py map:=$R.yaml > /tmp/review_loc.log 2>&1 &
LPID=$!
for i in $(seq 1 24); do sleep 5; timeout 3 ros2 lifecycle get /amcl 2>/dev/null | grep -q active && break; done
echo "amcl: $(timeout 3 ros2 lifecycle get /amcl 2>/dev/null)"
python3 - <<'PY'
import json, rclpy, time
from geometry_msgs.msg import PoseWithCovarianceStamped
s = json.load(open('/home/jetson/.config/project_atlas/localization_seed_pose.rejected-session-21ed0671.json'))
rclpy.init(); n = rclpy.create_node('review_seed'); p = n.create_publisher(PoseWithCovarianceStamped, '/initialpose', 10)
m = PoseWithCovarianceStamped(); m.header.frame_id = 'map'
m.pose.pose.position.x, m.pose.pose.position.y = s['x'], s['y']; m.pose.pose.orientation.z, m.pose.pose.orientation.w = s['qz'], s['qw']
m.pose.covariance[0] = m.pose.covariance[7] = 0.01; m.pose.covariance[35] = 0.005
for _ in range(5): m.header.stamp = n.get_clock().now().to_msg(); p.publish(m); time.sleep(0.4)
print('seeded at final session pose', round(s['x'], 3), round(s['y'], 3))
PY
sleep 30
python3 - <<'PY'
import json, math, sys, time, rclpy
sys.path.insert(0, '/home/jetson/project_atlas/scripts')
from pathlib import Path
from rclpy.action import ActionClient
from nav2_msgs.action import ComputePathToPose
from geometry_msgs.msg import PoseStamped, PolygonStamped
from sensor_msgs.msg import LaserScan
from rclpy.qos import qos_profile_sensor_data
from tf2_ros import Buffer, TransformListener
from atlas_map_acceptance_core import polygon_dimensions
from atlas_scan_fit_core import ScanFitPolicy, evaluate, load_occupied_index, unused_beam_points
places = json.load(open('/home/jetson/.config/project_atlas/named_places.json'))
dr = dict(places['dhruv room'], x=0.08, y=0.54); hall = places['hall']
rclpy.init(); n = rclpy.create_node('review_plan_only'); buf = Buffer(); TransformListener(buf, n)
st = {'fp': None, 'scan': None}
n.create_subscription(PolygonStamped, '/global_costmap/published_footprint', lambda m: st.__setitem__('fp', ([(p.x, p.y) for p in m.polygon.points], m.header.frame_id, time.time())), 10)
n.create_subscription(LaserScan, '/scan', lambda m: st.__setitem__('scan', m), qos_profile_sensor_data)
t = time.time()
while time.time() - t < 30 and (st['fp'] is None or st['scan'] is None or time.time() - t < 6): rclpy.spin_once(n, timeout_sec=0.1)
print('footprint seen:', st['fp'] is not None, 'after %.0fs' % (time.time() - t), flush=True)
def yaw(q): return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
out = {}
tr = buf.lookup_transform('map', 'base_link', rclpy.time.Time()); lt = buf.lookup_transform('base_link', 'laser_frame', rclpy.time.Time())
pose = (tr.transform.translation.x, tr.transform.translation.y, yaw(tr.transform.rotation))
laser = (lt.transform.translation.x, lt.transform.translation.y, yaw(lt.transform.rotation))
pol = ScanFitPolicy(); s = st['scan']
idx = load_occupied_index(Path('/home/jetson/project_atlas/maps/review_remap13.yaml'), Path('/home/jetson/project_atlas/maps/review_remap13.pgm'))
r = evaluate(unused_beam_points(s.angle_min, s.angle_increment, s.ranges, s.range_min, s.range_max, pol), pose, laser, idx, 0.1, pol)
out['amcl_pose_on_candidate'] = [round(v, 3) for v in pose]
out['live_scan_fit_on_candidate'] = {'ok': r.ok, 'fit': r.fit_fraction, 'reason': r.reason}
c = ActionClient(n, ComputePathToPose, '/compute_path_to_pose'); assert c.wait_for_server(timeout_sec=15)
def ps(p):
    m = PoseStamped(); m.header.frame_id = 'map'; m.header.stamp = n.get_clock().now().to_msg()
    m.pose.position.x, m.pose.position.y = float(p['x']), float(p['y']); m.pose.orientation.z, m.pose.orientation.w = float(p.get('qz', 0)), float(p.get('qw', 1)); return m
for key, a, b in (('forward', dr, hall), ('reverse', hall, dr)):
    g = ComputePathToPose.Goal(); g.start, g.goal, g.use_start = ps(a), ps(b), True
    f = c.send_goal_async(g); rclpy.spin_until_future_complete(n, f, timeout_sec=10); h = f.result()
    rf = h.get_result_async(); rclpy.spin_until_future_complete(n, rf, timeout_sec=25); res = rf.result()
    P = res.result.path.poses
    L = sum(math.hypot(q.pose.position.x - p.pose.position.x, q.pose.position.y - p.pose.position.y) for p, q in zip(P, P[1:]))
    out[key] = {'passed': res.status == 4 and len(P) >= 2, 'status': int(res.status), 'poses': len(P), 'path_length_m': round(L, 3)}
    print(key, out[key], flush=True)
print('scan fit', out['live_scan_fit_on_candidate'], 'pose', out['amcl_pose_on_candidate'], flush=True)
for _ in range(200):
    if st['fp'] is not None: break
    rclpy.spin_once(n, timeout_sec=0.1)
if st['fp'] is None:
    out['footprint'] = None; print('NO FOOTPRINT on /global_costmap/published_footprint', flush=True)
else:
    pts, frame, seen = st['fp']; d = polygon_dimensions(pts); d.update({'frame_id': frame, 'observed_unix': seen}); out['footprint'] = d
json.dump(out, open('/tmp/review_remap13.json', 'w'), indent=1); print(json.dumps(out))
PY
