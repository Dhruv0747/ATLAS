#!/usr/bin/env python3
"""Offline coloured 3D map from a recorded drive (read-only; runs on the Jetson, low priority).

Inputs:  BASE bag (domain 0: /tf map->odom from SLAM, /odom)  +  ASTRA bag (domain 77: depth 160x120 + colour 640x480).
Pose of each depth frame = SLAM map pose (map->odom o odom->base_link). Depth pixels -> base_link via the Astra mount
(config/astra_obstacles.yaml) -> map. Colour: the same ray projected into the colour image (factory intrinsics are
identical up to scale; the depth->colour offset message was not recorded, so the two optical centres are assumed equal
in version 1). Keyframes every 0.08 m or 4 deg. 2 cm voxel grid with averaged colour.
Outputs: OUT.ply (binary, coloured) and OUT.json (dashboard format: points_cm, rgb, path_cm).
Usage: build_colour_map.py BASE_BAG ASTRA_BAG OUT_PREFIX [NAME] [BASE_BAG2 ASTRA_BAG2 ...]
"""
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import yaml
import os
from rclpy.serialization import deserialize_message
sys.path.insert(0, '/home/jetson/project_atlas/scripts')
from atlas_icp_odometry_core import IcpConfig, icp, scan_to_points  # noqa: E402
from scipy.spatial import cKDTree  # noqa: E402
from rosidl_runtime_py.utilities import get_message
import rosbag2_py

ROOT = Path('/home/jetson/project_atlas')
VOXEL = 0.02
KEY_DIST, KEY_YAW = 0.03, math.radians(2.0)
ZMIN, ZMAX = 0.3, 3.5          # trusted depth range (m)
MAX_TURN_RATE = math.radians(float(__import__('os').environ.get('MAX_TURN_DEG', '8')))   # rad/s
DEPTH_TIME_OFFSET = float(__import__('os').environ.get('DEPTH_DT', '0'))   # s added to depth stamps
T_END = float(__import__('os').environ.get('T_END', '1e18'))


def reader(bag, topics):
    r = rosbag2_py.SequentialReader()
    r.open(rosbag2_py.StorageOptions(uri=bag, storage_id='sqlite3'), rosbag2_py.ConverterOptions('cdr', 'cdr'))
    types = {t.name: t.type for t in r.get_all_topics_and_types()}
    r.set_filter(rosbag2_py.StorageFilter(topics=[t for t in topics if t in types]))
    while r.has_next():
        name, data, t_ns = r.read_next()
        yield name, deserialize_message(data, get_message(types[name])), t_ns * 1e-9


def yaw_of(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


def stamp(m):
    return m.header.stamp.sec + m.header.stamp.nanosec * 1e-9


def slam_poses(base_bag):
    mo, od = [], []
    for name, m, _ in reader(base_bag, ['/tf', '/odom']):
        if name == '/tf':
            for tr in m.transforms:
                if tr.header.frame_id == 'map' and tr.child_frame_id == 'odom':
                    mo.append((stamp(tr), tr.transform.translation.x, tr.transform.translation.y, yaw_of(tr.transform.rotation)))
        else:
            od.append((stamp(m), m.pose.pose.position.x, m.pose.pose.position.y, yaw_of(m.pose.pose.orientation)))
    mo, od = np.array(mo), np.array(od)
    mo = mo[np.argsort(mo[:, 0])]; od = od[np.argsort(od[:, 0])]
    t = od[:, 0]
    mx, my = np.interp(t, mo[:, 0], mo[:, 1]), np.interp(t, mo[:, 0], mo[:, 2])
    myaw = np.interp(t, mo[:, 0], np.unwrap(mo[:, 3]))
    x = mx + np.cos(myaw) * od[:, 1] - np.sin(myaw) * od[:, 2]
    y = my + np.sin(myaw) * od[:, 1] + np.cos(myaw) * od[:, 2]
    yaw = myaw + np.unwrap(od[:, 3])
    valid = (t >= mo[0, 0]) & (t <= mo[-1, 0])
    return t[valid], x[valid], y[valid], yaw[valid]


def image_array(m):
    if m.encoding in ('16UC1', 'mono16'):
        return np.frombuffer(m.data, dtype=np.uint16).reshape(m.height, m.width).astype(np.float32) / 1000.0
    a = np.frombuffer(m.data, dtype=np.uint8).reshape(m.height, m.width, -1)[:, :, :3]
    return a[:, :, ::-1] if m.encoding.lower().startswith('bgr') else a


def merge(acc, keys_list, cols_list):
    """Voxel accumulator: (unique keys, colour sums, hit counts)."""
    if not keys_list:
        return acc
    K = np.concatenate(keys_list); S = np.concatenate(cols_list).astype(np.float64); N = np.ones(len(K))
    if acc is not None:
        K = np.concatenate([acc[0], K]); S = np.concatenate([acc[1], S]); N = np.concatenate([acc[2], N])
    uniq, inv = np.unique(K, axis=0, return_inverse=True); inv = inv.ravel()
    sums = np.zeros((len(uniq), 3)); np.add.at(sums, inv, S)
    cnt = np.zeros(len(uniq)); np.add.at(cnt, inv, N)
    return uniq, sums, cnt


def load_map_points(prefix):
    """Occupied cells of a saved 2D map (pgm + yaml) as map-frame points."""
    meta = yaml.safe_load(Path(prefix + '.yaml').read_text())
    raw = Path(prefix + '.pgm').read_bytes()
    parts = raw.split(maxsplit=4)               # P5 w h maxval data
    w, h = int(parts[1]), int(parts[2])
    img = np.frombuffer(parts[4][-w * h:], dtype=np.uint8).reshape(h, w)
    rows, cols = np.nonzero(img < 50)
    res, ox, oy = meta['resolution'], meta['origin'][0], meta['origin'][1]
    return np.c_[ox + (cols + 0.5) * res, oy + (h - 1 - rows + 0.5) * res]


def load_scans(base_bag):
    out = []
    for _, m, _ in reader(base_bag, ['/scan']):
        out.append((stamp(m), np.asarray(m.ranges, dtype=np.float32), m.angle_min, m.angle_increment))
    return out


def build(pairs, out, name):
    cfg = yaml.safe_load((ROOT / 'config/astra_obstacles.yaml').read_text())['mount']
    mx, my, mz = cfg['x_m'], cfg['y_m'], cfg['z_m']
    import os
    pitch = math.radians(float(os.environ.get('MOUNT_PITCH_DEG', cfg['pitch_deg'])))
    myaw = math.radians(float(os.environ.get('MOUNT_YAW_DEG', cfg['yaw_deg'])))
    map_prefix = os.environ.get('REFINE_MAP')
    mpts = load_map_points(map_prefix) if map_prefix else None
    mtree = cKDTree(mpts) if mpts is not None else None
    icfg = IcpConfig(coarse_match_m=0.3, fine_match_m=0.10, min_matches=30)
    keys_all, cols_all, path = [], [], []
    acc = None
    stats = dict(depth=0, keyframes=0, no_pose=0, no_colour=0)
    for base_bag, astra_bag in pairs:
        t_from = 0.0
        if '@' in astra_bag:
            astra_bag, t_from = astra_bag.split('@'); t_from = float(t_from)
        T, X, Y, YAW = slam_poses(base_bag)
        scans = load_scans(base_bag) if mtree is not None else []
        st = np.array([x[0] for x in scans]) if scans else None
        keep_t = T >= t_from; T, X, Y, YAW = T[keep_t], X[keep_t], Y[keep_t], YAW[keep_t]
        print(f'{Path(base_bag).parent.name}: {len(T)} SLAM poses {time.strftime("%H:%M:%S", time.localtime(T[0]))}-'
              f'{time.strftime("%H:%M:%S", time.localtime(T[-1]))}', flush=True)
        ci_d = ci_c = None; colours = []; last_key = None
        for topic, m, _ in reader(astra_bag, ['/astra/depth/camera_info', '/astra/color/camera_info',
                                                '/astra/color/image_raw', '/astra/depth/image_raw']):
            if topic == '/astra/depth/camera_info': ci_d = ci_d or m; continue
            if topic == '/astra/color/camera_info': ci_c = ci_c or m; continue
            if topic == '/astra/color/image_raw':
                colours.append((stamp(m), m)); colours = colours[-8:]; continue
            stats['depth'] += 1
            t = stamp(m) + DEPTH_TIME_OFFSET
            if t > T_END: break
            if ci_d is None or ci_c is None or not colours: continue
            if t < T[0] or t > T[-1]: stats['no_pose'] += 1; continue
            px, py, pyaw = np.interp(t, T, X), np.interp(t, T, Y), np.interp(t, T, YAW)
            rate = abs(np.interp(t + 0.25, T, YAW) - np.interp(t - 0.25, T, YAW)) / 0.5
            if rate > MAX_TURN_RATE:          # timing errors smear walls into arcs while turning: skip
                stats['turning'] = stats.get('turning', 0) + 1; continue
            if last_key and math.hypot(px - last_key[0], py - last_key[1]) < KEY_DIST and abs(pyaw - last_key[2]) < KEY_YAW:
                continue
            t_raw = t - DEPTH_TIME_OFFSET
            ct, cm = min(colours, key=lambda c: abs(c[0] - t_raw))
            if abs(ct - t_raw) > 0.12: stats['no_colour'] += 1; continue
            raw_key = (px, py, pyaw)
            if mtree is not None:          # refine the SLAM pose: this moment's LiDAR scan vs the 2D map
                k = int(np.argmin(np.abs(st - t)))
                if abs(st[k] - t) < 0.08:
                    sc = scans[k]
                    P = scan_to_points(sc[1], sc[2], sc[3], -0.05, 0.0, math.pi, icfg)
                    r = icp(P, mpts, (pyaw, px, py), icfg, mtree)
                    if r and r[3] > 0.7 and math.hypot(r[1] - px, r[2] - py) < 0.4 and abs(r[0] - pyaw) < math.radians(8):
                        stats['refined'] = stats.get('refined', 0) + 1
                        stats['shift_sum'] = stats.get('shift_sum', 0.0) + math.hypot(r[1] - px, r[2] - py)
                        px, py, pyaw = r[1], r[2], r[0]
                    else:
                        stats['refine_failed'] = stats.get('refine_failed', 0) + 1
            last_key = raw_key; stats['keyframes'] += 1; path.append((px, py))
            depth = image_array(m); rgb = image_array(cm)
            fx, fy, cx, cy = ci_d.k[0], ci_d.k[4], ci_d.k[2], ci_d.k[5]
            valid = (depth > ZMIN) & (depth < ZMAX)
            v, u = np.nonzero(valid)
            z = depth[v, u]; xo = (u - cx) * z / fx; yo = (v - cy) * z / fy          # optical: x right, y down, z fwd
            # colour pixel of the same ray
            uc = np.clip(np.round(ci_c.k[0] * xo / z + ci_c.k[2]).astype(int), 0, rgb.shape[1] - 1)
            vc = np.clip(np.round(ci_c.k[4] * yo / z + ci_c.k[5]).astype(int), 0, rgb.shape[0] - 1)
            col = rgb[vc, uc]
            # optical -> astra_link (x fwd, y left, z up) -> base_link (pitch about y, yaw about z, then offset)
            lx, ly, lz = z, -xo, -yo
            cp, sp = math.cos(pitch), math.sin(pitch)
            bx, bz = cp * lx + sp * lz, -sp * lx + cp * lz
            cyw, syw = math.cos(myaw), math.sin(myaw)
            bx, by = cyw * bx - syw * ly + mx, syw * bx + cyw * ly + my
            bz = bz + mz
            c, s = math.cos(pyaw), math.sin(pyaw)
            wx, wy = px + c * bx - s * by, py + s * bx + c * by
            keys = np.floor(np.c_[wx, wy, bz] / VOXEL).astype(np.int32)
            keys_all.append(keys); cols_all.append(col.astype(np.uint32))
            if len(keys_all) >= 40:
                acc = merge(acc, keys_all, cols_all); keys_all, cols_all = [], []
            if stats['keyframes'] % 200 == 0:
                print(f'  keyframes {stats["keyframes"]}', flush=True)
    acc = merge(acc, keys_all, cols_all)
    uniq, sums, cnt = acc
    rgb = (sums / cnt[:, None]).astype(np.uint8)
    keep = cnt >= 3                                              # drop rarely-seen voxels (noise, people)
    P = (uniq[keep] + 0.5) * VOXEL; RGB = rgb[keep]
    k5 = np.unique(np.floor(P / 0.05).astype(np.int32), axis=0)
    print(f'stats {stats}; voxels {len(uniq)}, kept {keep.sum()}; sharpness: 5 cm cells occupied {len(k5)} (fewer = sharper)', flush=True)
    with open(f'{out}.ply', 'wb') as f:
        f.write((f'ply\nformat binary_little_endian 1.0\nelement vertex {len(P)}\nproperty float x\nproperty float y\n'
                 f'property float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n').encode())
        rec = np.zeros(len(P), dtype=[('x', '<f4'), ('y', '<f4'), ('z', '<f4'), ('r', 'u1'), ('g', 'u1'), ('b', 'u1')])
        rec['x'], rec['y'], rec['z'] = P[:, 0], P[:, 1], P[:, 2]; rec['r'], rec['g'], rec['b'] = RGB[:, 0], RGB[:, 1], RGB[:, 2]
        f.write(rec.tobytes())
    # dashboard copy: 5 cm voxels, at most 60k points
    k5 = np.floor(P / 0.05).astype(np.int32)
    u5, i5 = np.unique(k5, axis=0, return_index=True)
    sel = i5 if len(i5) <= 60000 else np.random.default_rng(0).choice(i5, 60000, replace=False)
    pts = np.round(P[sel] * 100).astype(int); cols = RGB[sel].astype(int)
    path_cm = [int(round(v * 100)) for p in path[::5] for v in (p[0], p[1], 0)]
    Path(f'{out}.json').write_text(json.dumps({
        'seq': int(time.time()), 'unix': time.time(), 'live': False, 'name': name, 'colour': True,
        'points_total': int(len(P)), 'points_shown': int(len(sel)),
        'points_cm': pts.ravel().tolist(), 'rgb': ((cols[:, 0] << 16) | (cols[:, 1] << 8) | cols[:, 2]).tolist(),
        'path_cm': path_cm}))
    print(f'wrote {out}.ply ({len(P)} points, 2 cm) and {out}.json ({len(sel)} points, 5 cm)')


if __name__ == '__main__':
    a = sys.argv[1:]
    out, name = a[2], (a[3] if len(a) > 3 else 'Colour map')
    pairs = [(a[0], a[1])] + [(a[i], a[i + 1]) for i in range(4, len(a) - 1, 2)]
    build(pairs, out, name)
