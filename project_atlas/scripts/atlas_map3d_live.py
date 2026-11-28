#!/usr/bin/env python3
"""Live 3D map feed for the dashboard (read-only; ROS domain 77; started with the M3 mapping launch).

Every 3 s: RTAB-Map's assembled map (/cloud_map, PointCloud2) -> drop points below the floor (glossy-floor mirror
image) and above 2.5 m -> 5 cm voxel grid -> at most 10,000 points -> web/v2/map3d_live.txt (JSON, integer cm),
plus the rover's position from /odom. Written atomically; the dashboard's static V2 route serves it (no-cache).
No control output of any kind.
"""
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'web' / 'v2' / 'map3d_live.txt'
PERIOD_S, VOXEL_M, MAX_POINTS = 3.0, 0.05, 10000
Z_MIN, Z_MAX = -0.05, 2.5


def reduce_cloud(xyz, voxel=VOXEL_M, max_points=MAX_POINTS, seed=0):
    """(N,3) float -> (M,3) int16 centimetres: finite, Z_MIN..Z_MAX, one point per voxel, at most max_points."""
    xyz = np.asarray(xyz, dtype=np.float64).reshape(-1, 3)
    xyz = xyz[np.isfinite(xyz).all(axis=1)]
    xyz = xyz[(xyz[:, 2] >= Z_MIN) & (xyz[:, 2] <= Z_MAX)]
    if xyz.size == 0:
        return np.zeros((0, 3), np.int16)
    keys = np.floor(xyz / voxel).astype(np.int64)
    _, idx = np.unique(keys, axis=0, return_index=True)
    xyz = xyz[np.sort(idx)]
    if len(xyz) > max_points:
        xyz = xyz[np.sort(np.random.default_rng(seed).choice(len(xyz), max_points, replace=False))]
    return np.clip(np.round(xyz * 100), -32000, 32000).astype(np.int16)


def write_atomic(path, text):
    tmp = path.with_name('.' + path.name + '.tmp')
    tmp.write_text(text)
    os.replace(tmp, path)


def main():
    try:
        os.nice(10)
    except OSError:
        pass
    import rclpy
    from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
    from sensor_msgs.msg import PointCloud2
    from nav_msgs.msg import Odometry
    from sensor_msgs_py import point_cloud2

    rclpy.init()
    node = rclpy.create_node('atlas_map3d_live')
    state = {'cloud': None, 'odom': None, 'seq': 0, 'last': 0.0, 'new': False}

    def on_cloud(m):
        state['cloud'], state['new'] = m, True

    def on_odom(m):
        p, q = m.pose.pose.position, m.pose.pose.orientation
        state['odom'] = (p.x, p.y, math.degrees(math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))))

    node.create_subscription(PointCloud2, '/cloud_map', on_cloud,
                             QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE))
    node.create_subscription(Odometry, '/odom', on_odom, 10)

    def tick():
        # Rewritten every tick while this feed runs (it only runs during a mapping session), so the dashboard can tell
        # "mapping live" even when RTAB-Map publishes no new cloud (parked rover = unchanged map). Points are only
        # re-reduced when a new cloud arrived; the rover position is refreshed every time.
        if state['cloud'] is None:
            return
        try:
            m = state['cloud']
            if state['new'] or state.get('pts') is None:
                xyz = point_cloud2.read_points_numpy(m, field_names=('x', 'y', 'z'), skip_nans=True)
                state['pts'], state['total'], state['new'] = reduce_cloud(xyz), int(len(xyz)), False
            pts, total = state['pts'], state['total']
            state['seq'] += 1
            o = state['odom']
            write_atomic(OUT, json.dumps({
                'seq': state['seq'], 'unix': round(time.time(), 1), 'frame': m.header.frame_id,
                'points_total': total, 'points_shown': int(len(pts)), 'voxel_m': VOXEL_M,
                'robot_cm_deg': [round(o[0] * 100), round(o[1] * 100), round(o[2], 1)] if o else None,
                'points_cm': pts.reshape(-1).tolist()}, separators=(',', ':')))
        except Exception as e:
            node.get_logger().warning('map3d live frame skipped: ' + str(e)[:120], throttle_duration_sec=30.0)

    node.create_timer(PERIOD_S, tick)
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    sys.exit(main())
