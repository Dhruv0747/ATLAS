#!/usr/bin/env python3
"""Replay a recorded mapping session through the STAGED final-map consistency path, exactly as mission control would
(2 scans/s, SLAM live map->base_link pose, candidate bytes), then re-run acceptance with the stored evidence."""
import glob, json, math, sys, time, numpy as np, rosbag2_py
sys.path.insert(0, '/home/jetson/atlas_staging_20261113/scripts')
import atlas_final_map_consistency as F
import atlas_map_acceptance_core as A
from atlas_scan_fit_core import load_occupied_points
from pathlib import Path
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import LaserScan
from tf2_msgs.msg import TFMessage
SID = sys.argv[1] if len(sys.argv) > 1 else 'de55c1d3'
B = glob.glob(f'/home/jetson/project_atlas/data/demonstrations/manual_mapping_{SID}*')[0]
pref = glob.glob(f'/home/jetson/project_atlas/maps/.atlas_candidate_{SID}*.yaml')[0][:-5]
sess = json.load(open(f'/home/jetson/.config/project_atlas/rejected_session_{SID}/mapping_session.json'))
yaw = lambda q: math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
buf = F.ScanSampleBuffer(); buf.begin(sess['id'])
r = rosbag2_py.SequentialReader(); r.open(rosbag2_py.StorageOptions(uri=B, storage_id='sqlite3'), rosbag2_py.ConverterOptions('cdr', 'cdr'))
r.set_filter(rosbag2_py.StorageFilter(topics=['/scan', '/tf'])); mo = ob = None
while r.has_next():
    n, d, t = r.read_next(); ts = t * 1e-9
    if n == '/tf':
        for tr in deserialize_message(d, TFMessage).transforms:
            p = (tr.transform.translation.x, tr.transform.translation.y, yaw(tr.transform.rotation))
            if tr.header.frame_id == 'map' and tr.child_frame_id == 'odom': mo = p
            elif tr.header.frame_id == 'odom' and tr.child_frame_id == 'base_link': ob = p
        continue
    if ts < sess['ready_unix'] or mo is None or ob is None: continue
    s = deserialize_message(d, LaserScan)
    c, si = math.cos(mo[2]), math.sin(mo[2])
    buf.add(ts, (mo[0] + c*ob[0] - si*ob[1], mo[1] + si*ob[0] + c*ob[1], mo[2] + ob[2]), s.ranges, s.angle_min, s.angle_increment)
occ = np.asarray(load_occupied_points(Path(pref + '.yaml'), Path(pref + '.pgm')), dtype=float)
t0 = time.monotonic(); ev = F.evaluate(buf.samples, occ, (-0.05, 0.0, math.pi), buf.policy, session_id=sess['id'])
ev['evaluation_s'] = round(time.monotonic() - t0, 2); ev['thinned'] = buf.dropped
print('final_map_consistency:', json.dumps({k: v for k, v in ev.items() if k != 'policy'}))
stored = json.load(open(pref + '.acceptance.json'))
print('\nstored decision:', stored.get('decision'))
for f in stored.get('failures', []): print('  was:', f)
stored['final_map_consistency'] = ev
kw = dict(expected_session_id=sess['id'], expected_candidate_map_id=stored['candidate_map_id'],
          session_started_unix=float(sess.get('ready_unix', sess['started_unix'])), evaluated_unix=stored['evaluated_unix'],
          source_floor_unix=float(sess['started_unix']))
for on in (False, True):
    out = A.evaluate_acceptance_evidence(stored, policy=A.MapAcceptancePolicy(final_map_replaces_tf_jump=on), **kw)
    print(f'\nswitch {"ON " if on else "OFF"}: {"ACCEPT" if not out else "REJECT"}')
    for f in out: print('  ', f)
