"""Read-only endpoint/map consistency at the largest recorded map correction.

Uses a map received BEFORE the scan window. This is not SLAM's internal
correspondence trace and cannot establish which constraint its optimizer chose.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


def pose(transform):
    q = transform.rotation
    return np.array([transform.translation.x, transform.translation.y,
                     math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))])


def compose(a, b):
    c, s = math.cos(a[2]), math.sin(a[2])
    return np.array([a[0]+c*b[0]-s*b[1], a[1]+s*b[0]+c*b[1], a[2]+b[2]])


def points_at(points, p):
    c, s = np.cos(p[2]), np.sin(p[2])
    return points @ np.array([[c,s],[-s,c]]) + p[:2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bag')
    parser.add_argument('output', help='New JSON report, never overwritten')
    args = parser.parse_args()
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=args.bag, storage_id='sqlite3'), rosbag2_py.ConverterOptions('', ''))
    types = {t.name: get_message(t.type) for t in reader.get_all_topics_and_types()}
    corrections, odom, scans, maps, static = [], [], [], [], {}
    while reader.has_next():
        topic, data, record = reader.read_next()
        if topic not in {'/tf', '/tf_static', '/scan', '/map'}:
            continue
        m = deserialize_message(data, types[topic])
        receipt = record*1e-9
        if topic == '/map':
            maps.append((receipt,m))
        elif topic == '/scan':
            scans.append((m.header.stamp.sec+m.header.stamp.nanosec*1e-9, receipt,m))
        else:
            for t in m.transforms:
                pair = (t.header.frame_id.strip('/'),t.child_frame_id.strip('/'))
                if topic == '/tf_static':
                    static[pair] = pose(t.transform)
                elif pair == ('map','odom'):
                    corrections.append((receipt,pose(t.transform)))
                elif pair == ('odom','base_link'):
                    odom.append((t.header.stamp.sec+t.header.stamp.nanosec*1e-9,*pose(t.transform)))
    if len(corrections)<2:
        raise SystemExit('No map correction pair')
    before,after = max(zip(corrections,corrections[1:]),key=lambda pair: np.linalg.norm(pair[1][1][:2]-pair[0][1][:2]))
    event = after[0]
    candidates = [s for s in scans if event-0.8 <= s[0] <= event+0.3]
    if not candidates:
        raise SystemExit('No event scans')
    old_maps = [m for m in maps if m[0] < min(s[0] for s in candidates)]
    if not old_maps:
        raise SystemExit('No uncontaminated prior map')
    map_time,m = old_maps[-1]
    grid = np.asarray(m.data).reshape(m.info.height,m.info.width)
    ys,xs = np.nonzero(grid>=65)
    q = m.info.origin.orientation
    origin = np.array([m.info.origin.position.x,m.info.origin.position.y,
                       math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))])
    occupied = points_at(np.c_[(xs+.5)*m.info.resolution,(ys+.5)*m.info.resolution],origin)
    if not len(occupied):
        raise SystemExit('Prior map has no occupied cells')
    tree = cKDTree(occupied)
    extrinsic = compose(static[('base_link','base_footprint')],static[('base_footprint','laser_frame')])
    values = np.asarray(sorted(odom))
    values[:,3] = np.unwrap(values[:,3])
    rows=[]
    for t,receipt,scan in candidates:
        if scan.header.frame_id.strip('/')!='laser_frame' or not values[0,0]<=t<=values[-1,0]:
            continue
        base = np.array([np.interp(t,values[:,0],values[:,i]) for i in range(1,4)])
        ranges = np.asarray(scan.ranges)
        angles = scan.angle_min+np.arange(len(ranges))*scan.angle_increment
        valid = np.isfinite(ranges)&(ranges>=.3)&(ranges<=8)
        points = np.c_[ranges[valid]*np.cos(angles[valid]), ranges[valid]*np.sin(angles[valid])]
        if not len(points):
            continue
        row={'scan_seconds_from_jump':t-event,'valid_points':len(points),'hypotheses':{}}
        robot_before=compose(before[1],base)
        robot_after=compose(after[1],base)
        row['same_time_robot_position_correction_m']=float(np.linalg.norm(robot_after[:2]-robot_before[:2]))
        row['same_time_robot_yaw_correction_deg']=math.degrees(math.atan2(math.sin(robot_after[2]-robot_before[2]),math.cos(robot_after[2]-robot_before[2])))
        for name,correction in [('before',before[1]),('after',after[1])]:
            projected = points_at(points,compose(compose(correction,base),extrinsic))
            distance,_=tree.query(projected)
            # World points to map-grid frame, honoring origin yaw.
            local = points_at(projected-origin[:2],[0,0,-origin[2]])
            cell = np.floor(local/m.info.resolution).astype(int)
            inside=(cell[:,0]>=0)&(cell[:,0]<m.info.width)&(cell[:,1]>=0)&(cell[:,1]<m.info.height)
            known=np.zeros(len(points),dtype=bool)
            free=np.zeros(len(points),dtype=bool)
            known[inside]=grid[cell[inside,1],cell[inside,0]]>=0
            free[inside]=grid[cell[inside,1],cell[inside,0]]==0
            row['hypotheses'][name]={'median_endpoint_distance_m':float(np.median(distance)),
                                      'p90_endpoint_distance_m':float(np.percentile(distance,90)),
                                      'within_10cm_fraction':float(np.mean(distance<=.1)),
                                      'known_endpoint_fraction':float(np.mean(known)),
                                      'free_endpoint_fraction':float(np.mean(free))}
        rows.append(row)
    report={'event_unix':event,'prior_map_age_s':event-map_time,'resolution_m':m.info.resolution,
            'map_before':before[1].tolist(),'map_after':after[1].tolist(),'rows':rows,
            'limitations':'Frozen prior occupancy grid, not SLAM internal submap/constraints. Recorded TF timing retained; no deskew. Endpoint distance alone ignores visibility, dynamics and free-space rays; no causal or deployment verdict.'}
    with Path(args.output).open('x') as target:
        json.dump(report,target,indent=2)
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
