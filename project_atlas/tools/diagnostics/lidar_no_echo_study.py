#!/usr/bin/env python3
"""Offline (read-only) root-cause study of LiDAR no-echo rays. 2026-11-15.

For every k-th /scan_raw of a mapping recording, the laser pose (map->odom->base_link from /tf, static laser mount)
is used to ray-cast each ray on that session's own occupancy map. Rays with NO echo are classified by what the map
says they should have hit: nothing within 12 m / beyond-map (open), wall too close (< range_min), glancing incidence
(> GLANCE_DEG between ray and wall normal), or a normal-incidence wall (surface/reflectivity or unmapped object).
Valid-echo rays get the same classification for comparison (echo rate per class).
Usage: lidar_no_echo_study.py <bag_dir> <map.yaml> [every_n]
"""
import bisect, math, os, sys
from collections import Counter, defaultdict
import numpy as np, yaml
import rosbag2_py
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import LaserScan
from tf2_msgs.msg import TFMessage

LASER = (-0.05, 0.0, math.pi)      # base_link -> laser_frame (x, y, yaw)
GLANCE_DEG = 70.0


def load_map(path):
    meta = yaml.safe_load(open(path))
    pgm = os.path.join(os.path.dirname(path), meta['image'])
    with open(pgm, 'rb') as f:
        assert f.readline().strip() == b'P5'
        line = f.readline()
        while line.startswith(b'#'):
            line = f.readline()
        w, h = map(int, line.split()); f.readline()
        img = np.frombuffer(f.read(w * h), dtype=np.uint8).reshape(h, w)
    occ = (255 - img.astype(np.float64)) / 255.0 > meta.get('occupied_thresh', 0.65)
    return occ[::-1, :], meta['resolution'], meta['origin']      # row 0 = min y


def yaw_of(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


def compose(a, b):
    x, y, t = a; bx, by, bt = b
    return (x + bx * math.cos(t) - by * math.sin(t), y + bx * math.sin(t) + by * math.cos(t), t + bt)


def at(series, t):
    ts = series[0]
    i = bisect.bisect_right(ts, t) - 1
    return series[1][i] if i >= 0 and t - ts[i] < 0.5e9 else None


def main(bag, map_yaml, every=10):
    occ, res, origin = load_map(map_yaml)
    H, W = occ.shape
    # wall normals from the occupancy gradient
    gy, gx = np.gradient(occ.astype(np.float64))
    r = rosbag2_py.SequentialReader()
    r.open(rosbag2_py.StorageOptions(uri=bag, storage_id='sqlite3'), rosbag2_py.ConverterOptions('cdr', 'cdr'))
    r.set_filter(rosbag2_py.StorageFilter(topics=['/tf', '/scan_raw']))
    tf = {'map>odom': ([], []), 'odom>base_link': ([], [])}
    scans = []
    n = 0
    while r.has_next():
        topic, raw, t = r.read_next()
        if topic == '/tf':
            for tr in deserialize_message(raw, TFMessage).transforms:
                key = f'{tr.header.frame_id}>{tr.child_frame_id}'
                if key in tf:
                    st = tr.header.stamp.sec * 1_000_000_000 + tr.header.stamp.nanosec
                    p = tr.transform.translation
                    tf[key][0].append(st); tf[key][1].append((p.x, p.y, yaw_of(tr.transform.rotation)))
        else:
            n += 1
            if n % every == 0:
                scans.append(deserialize_message(raw, LaserScan))
    for k in tf:   # sort by stamp
        z = sorted(zip(*tf[k])) if tf[k][0] else []
        tf[k] = ([a for a, _ in z], [b for _, b in z])
    cls_all, cls_miss = Counter(), Counter()
    miss_by_bearing = defaultdict(Counter)
    used = 0
    cell_all, cell_miss = Counter(), Counter(); runs = Counter()
    for s in scans:
        st = s.header.stamp.sec * 1_000_000_000 + s.header.stamp.nanosec
        mo, ob = at(tf['map>odom'], st), at(tf['odom>base_link'], st)
        if mo is None or ob is None:
            continue
        used += 1
        lx, ly, lt = compose(compose(mo, ob), LASER)
        nr = len(s.ranges)
        ang = lt + s.angle_min + np.arange(nr) * s.angle_increment
        steps = np.arange(1, int(12.0 / res)) * res
        px = lx + np.outer(np.cos(ang), steps); py = ly + np.outer(np.sin(ang), steps)
        cx = ((px - origin[0]) / res).astype(int); cy = ((py - origin[1]) / res).astype(int)
        inside = (cx >= 0) & (cx < W) & (cy >= 0) & (cy < H)
        o = np.zeros_like(inside)
        o[inside] = occ[cy[inside], cx[inside]]
        # stop at the first cell leaving the map
        first_out = np.where(inside.all(1), steps.size, np.argmin(inside, 1))
        first_hit = np.where(o.any(1), np.argmax(o, 1), steps.size)
        for i, d in enumerate(s.ranges):
            a = ang[i]; ca, sa = math.cos(a), math.sin(a)
            j = first_hit[i]
            hit = None if j >= first_out[i] else (steps[j], cx[i, j], cy[i, j])
            if hit is None:
                c = 'open (no wall within 12 m / map)'
            elif hit[0] < max(s.range_min, 0.16):
                c = 'wall closer than range_min'
            else:
                nx, ny = -gx[hit[2], hit[1]], -gy[hit[2], hit[1]]
                nn = math.hypot(nx, ny)
                inc = 0.0 if nn == 0 else math.degrees(math.acos(min(1.0, abs(ca * nx + sa * ny) / nn)))
                band = 'near <1 m' if hit[0] < 1 else ('1-3 m' if hit[0] < 3 else '>3 m')
                c = f"{'GLANCING >70deg' if inc > GLANCE_DEG else 'normal incidence'} wall {band}"
            ok = math.isfinite(d) and s.range_min <= d <= s.range_max
            if hit is not None and hit[0] >= 0.16:
                key = (hit[1] // 3, hit[2] // 3)     # 15 cm cells
                cell_all[key] += 1
                if not ok:
                    cell_miss[key] += 1
            cls_all[c] += 1
            if not ok:
                cls_miss[c] += 1
                rb = int(((math.degrees(s.angle_min + i * s.angle_increment) + 180) % 360) // 30) * 30
                miss_by_bearing[rb][c] += 1
        run = 0
        for d in list(s.ranges) + [1.0]:
            if math.isfinite(d) and s.range_min <= d <= s.range_max:
                if run: runs[min(run, 20)] += 1
                run = 0
            else:
                run += 1
    tot_miss = sum(cls_miss.values()); tot = sum(cls_all.values())
    print(f'scans used {used}, rays {tot}, no-echo rays {tot_miss} ({100 * tot_miss / max(tot, 1):.1f} %)')
    print('class: share of all no-echo rays | no-echo rate within the class')
    for c, m in cls_miss.most_common():
        print(f'  {c:42s} {100 * m / tot_miss:5.1f} % | {100 * m / cls_all[c]:5.1f} % of {cls_all[c]} rays')
    seen = [k for k, v in cell_all.items() if v >= 20]
    rates = sorted(cell_miss[k] / cell_all[k] for k in seen)
    always = [k for k in seen if cell_miss[k] / cell_all[k] >= 0.7]
    miss_in_always = sum(cell_miss[k] for k in always)
    print(f'map wall cells seen >= 20 times: {len(seen)}; cells missing >= 70 %: {len(always)} '
          f'(hold {100 * miss_in_always / max(sum(cell_miss[k] for k in seen), 1):.0f} % of the no-echo rays); '
          f'median cell miss rate {100 * rates[len(rates) // 2]:.0f} %' if rates else 'no cells')
    print('no-echo run lengths (consecutive rays, 1 deg each):', dict(sorted(runs.items())))
    print('no-echo rays by robot-frame bearing sector (0 = front, 90 = left): top class')
    for b in sorted(miss_by_bearing):
        c = miss_by_bearing[b]; m = sum(c.values())
        print(f'  {b:3d}-{b + 30:3d} deg: {m:6d} no-echo; ' + ', '.join(f'{k} {100 * v / m:.0f}%' for k, v in c.most_common(2)))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 10)
