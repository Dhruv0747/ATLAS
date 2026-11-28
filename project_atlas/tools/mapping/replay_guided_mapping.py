#!/usr/bin/env python3
"""Offline replay of the guided mapping assistant on a saved bag (2026-11-16). No ROS needed; read-only.

Runs atlas_map_quality_core (per-area verdicts, frontiers, prompts) and atlas_invisible_objects_core (depth +
ultrasonic objects the LiDAR cannot see) on a recording, against a saved map, and writes:
  <out>.json  summary: tile counts, weak tiles, frontiers, prompts, invisible-object candidates (virtual_obstacles
              format, "candidate": true) and which confirmed virtual obstacles they overlap
  <out>.png   map + quality tiles (green accepted, amber weak) + driven path + invisible-object candidates
              (magenta) + map changes, i.e. LiDAR objects the saved map lacks (orange) + confirmed virtual obstacles
              (blue) + frontiers (cyan)

Pose: map->odom (latest at the stamp) composed with odom->base_link (nearest) from the bag's /tf.

Usage:
  python3 tools/mapping/replay_guided_mapping.py BAG_DIR MAP.yaml OUT_PREFIX [--places named_places.json]
         [--virtual config/virtual_obstacles.json] [--t0 S] [--t1 S]
"""
import argparse
import bisect
import json
import math
from pathlib import Path
import struct
import sys
import zlib

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[2] / 'scripts'))
import bag_reader  # noqa: E402
import atlas_invisible_objects_core as ioc  # noqa: E402
import atlas_map_quality_core as mq  # noqa: E402

LASER_IN_BASE = (-0.05, 0.0, math.pi)
US_MAX_AGE_S = 0.3


# ------------------------------------------------------------------ map io
def load_map(yaml_path):
    vals = {}
    for line in Path(yaml_path).read_text().splitlines():
        if ':' in line:
            k, v = line.split(':', 1)
            vals[k.strip()] = v.strip()
    image = Path(yaml_path).parent / vals['image']
    res = float(vals['resolution'])
    origin = [float(x) for x in vals['origin'].strip('[]').split(',')]
    occ, free = float(vals.get('occupied_thresh', 0.65)), float(vals.get('free_thresh', 0.25))
    negate = int(vals.get('negate', 0))
    raw = image.read_bytes()
    parts, pos = [], 0
    while len(parts) < 4:                                  # P5, width, height, maxval (skip comments)
        while raw[pos:pos + 1].isspace():
            pos += 1
        if raw[pos:pos + 1] == b'#':
            pos = raw.index(b'\n', pos) + 1
            continue
        end = pos
        while not raw[end:end + 1].isspace():
            end += 1
        parts.append(raw[pos:end])
        pos = end
    pos += 1
    if parts[0] != b'P5':
        raise ValueError('only binary PGM (P5) maps are supported')
    w, h, maxv = int(parts[1]), int(parts[2]), int(parts[3])
    pix = raw[pos:pos + w * h]
    data = [0] * (w * h)
    for row in range(h):
        gy = h - 1 - row                                    # PGM row 0 is the top; grid row 0 is origin_y
        for gx in range(w):
            raw_v = pix[row * w + gx]
            if raw_v == 205 and maxv == 255 and not negate:   # map_saver's unknown value: always unknown here
                data[gy * w + gx] = -1                      # (with free_thresh 0.25 the threshold rule alone
                continue                                    #  would call 205 free: 1 - 205/255 = 0.196 < 0.25)
            v = raw_v / maxv
            p = v if negate else 1.0 - v
            data[gy * w + gx] = 100 if p > occ else (0 if p < free else -1)
    return mq.Grid(w, h, res, origin[0], origin[1], data)


# ------------------------------------------------------------------ poses
class Poses:
    def __init__(self):
        self.mo_t, self.mo = [], []          # map->odom
        self.ob_t, self.ob = [], []          # odom->base_link

    def add_tf(self, edges):
        for stamp, parent, child, x, y, yaw in edges:
            if parent == 'map' and child == 'odom':
                self.mo_t.append(stamp)
                self.mo.append((x, y, yaw))
            elif parent == 'odom' and child == 'base_link':
                self.ob_t.append(stamp)
                self.ob.append((x, y, yaw))

    def finish(self):
        for tk, vk in (('mo_t', 'mo'), ('ob_t', 'ob')):
            pairs = sorted(zip(getattr(self, tk), getattr(self, vk)))
            setattr(self, tk, [p[0] for p in pairs])
            setattr(self, vk, [p[1] for p in pairs])

    def at(self, t, max_gap=0.3):
        i = bisect.bisect_right(self.mo_t, t) - 1
        if i < 0 or not self.ob_t:
            return None
        j = bisect.bisect_left(self.ob_t, t)
        cands = [k for k in (j - 1, j) if 0 <= k < len(self.ob_t)]
        k = min(cands, key=lambda k: abs(self.ob_t[k] - t))
        if abs(self.ob_t[k] - t) > max_gap:
            return None
        mx, my, ma = self.mo[i]
        ox, oy, oa = self.ob[k]
        return (mx + ox * math.cos(ma) - oy * math.sin(ma), my + ox * math.sin(ma) + oy * math.cos(ma),
                math.atan2(math.sin(ma + oa), math.cos(ma + oa)))

    def map_odom_series(self):
        return [(t, *v) for t, v in zip(self.mo_t, self.mo)]


# ------------------------------------------------------------------ png
def write_png(path, w, h, rgb):
    raw = b''.join(b'\x00' + bytes(rgb[y * w * 3:(y + 1) * w * 3]) for y in range(h))

    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
                           + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def render(grid, tracker, summary, candidates, confirmed, path, map_changes=(), scale=4):
    W, H = grid.w * scale, grid.h * scale
    img = bytearray(W * H * 3)

    def put(px, py, c, a=1.0):
        if 0 <= px < W and 0 <= py < H:
            o = (py * W + px) * 3
            for k in range(3):
                img[o + k] = int(img[o + k] * (1 - a) + c[k] * a)

    def world_px(x, y):
        return int((x - grid.ox) / grid.res * scale), int(H - 1 - (y - grid.oy) / grid.res * scale)

    for gy in range(grid.h):
        for gx in range(grid.w):
            v = grid.data[gy * grid.w + gx]
            c = (20, 20, 20) if v >= 65 else ((235, 235, 235) if v == 0 else (120, 120, 120))
            for dy in range(scale):
                for dx in range(scale):
                    put(gx * scale + dx, (grid.h - 1 - gy) * scale + dy, c)
    tm = summary['tile_m']
    for ix, iy, code, _ in summary['tiles']:
        c = (40, 200, 90) if code == 'A' else (255, 190, 0)
        x0, y0 = world_px(ix * tm, (iy + 1) * tm)
        x1, y1 = world_px((ix + 1) * tm, iy * tm)
        for py in range(y0, y1):
            for px in range(x0, x1):
                put(px, py, c, 0.35)

    def rect(poly, c, width=2):
        xs = [q[0] for q in poly]
        ys = [q[1] for q in poly]
        x0, y0 = world_px(min(xs), max(ys))
        x1, y1 = world_px(max(xs), min(ys))
        for k in range(width):
            for px in range(x0, x1 + 1):
                put(px, y0 + k, c)
                put(px, y1 - k, c)
            for py in range(y0, y1 + 1):
                put(x0 + k, py, c)
                put(x1 - k, py, c)
    for _, poly in confirmed:
        rect(poly, (40, 110, 255), 3)
    for c in map_changes:
        rect(c['polygon'], (255, 120, 0), 2)
    for c in candidates:
        rect(c['polygon'], (230, 0, 230), 2)
    for x, y in path:
        px, py = world_px(x, y)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                put(px + dx, py + dy, (0, 150, 60))
    for f in summary['frontiers']:
        px, py = world_px(f['x'], f['y'])
        for dx in range(-4, 5):
            put(px + dx, py, (0, 200, 255))
            put(px, py + dx, (0, 200, 255))
    return W, H, img


# ------------------------------------------------------------------ main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('bag')
    ap.add_argument('map_yaml')
    ap.add_argument('out')
    ap.add_argument('--places')
    ap.add_argument('--virtual')
    ap.add_argument('--t0', type=float, default=0.0, help='seconds from bag start')
    ap.add_argument('--t1', type=float, default=1e9)
    a = ap.parse_args(argv)

    grid = load_map(a.map_yaml)
    poses = Poses()
    for _, _, m in bag_reader.read(a.bag, {'/tf'}):
        poses.add_tf(m)
    poses.finish()
    if not poses.mo_t:
        raise SystemExit('no map->odom in /tf: was localization running?')

    quality = mq.QualityTracker()
    inv = ioc.InvisibleObjects()                           # depth / ultrasonic where the LiDAR has no echo
    changes = ioc.InvisibleObjects(ioc.MAP_CHANGE_POLICY)  # LiDAR returns where the saved map is free
    lidar, lidar_t = None, None
    last_seq = {}
    t_start = None
    counts = {'scans': 0, 'depth': 0, 'us': 0, 'no_pose': 0, 'map_change_scans': 0}
    for t, topic, m in bag_reader.read(a.bag, {'/scan', '/astra/obstacle_scan', '/ultrasonic/validity'}):
        t_start = t if t_start is None else t_start
        if not a.t0 <= t - t_start <= a.t1:
            continue
        if topic == '/scan':
            lidar = ioc.LidarSectors(m['angle_min'], m['angle_increment'], m['ranges'], m['range_min'],
                                     m['range_max'], LASER_IN_BASE)
            lidar_t = m['stamp']
            pose = poses.at(m['stamp'])
            if pose is None:
                counts['no_pose'] += 1
                continue
            if quality.add_scan(m['stamp'], pose, LASER_IN_BASE, m['angle_min'], m['angle_increment'],
                                m['ranges'], m['range_min'], m['range_max'], grid) is not None:
                counts['scans'] += 1
            if changes.add_unmapped_lidar(m['stamp'], pose, m['angle_min'], m['angle_increment'], m['ranges'],
                                          m['range_min'], m['range_max'], grid, LASER_IN_BASE):
                counts['map_change_scans'] += 1
        elif topic == '/astra/obstacle_scan':
            if lidar is None or abs(m['stamp'] - lidar_t) > 0.3:
                continue
            pose = poses.at(m['stamp'])
            if pose is not None and inv.add_depth(m['stamp'], pose, m['angle_min'], m['angle_increment'],
                                                  m['ranges'], lidar, grid):
                counts['depth'] += 1
        else:
            try:
                d = json.loads(m)
            except ValueError:
                continue
            if lidar is None or abs(t - lidar_t) > 0.5:
                continue
            pose = poses.at(t)
            for side in ('front', 'rear'):
                s = (d.get('sensors') or {}).get(side) or {}
                seq = s.get('sample_sequence')
                if s.get('state') != 'VALID' or seq == last_seq.get(side) or not isinstance(s.get('range_mm'), (int, float)) \
                        or not (s.get('sample_age_s') or 9) <= US_MAX_AGE_S or pose is None:
                    continue
                last_seq[side] = seq
                if inv.add_ultrasonic(t, pose, side, s['range_mm'] / 1000.0, lidar, grid):
                    counts['us'] += 1
    jumps = 0
    for t, dx, dyaw in mq.pose_jumps(poses.map_odom_series()):
        if t_start is not None and not a.t0 <= t - t_start <= a.t1:
            continue
        p = poses.at(t, max_gap=1.0)
        if p is not None and quality.add_jump(t, p[:2], dx, dyaw):
            jumps += 1

    places = {}
    if a.places:
        raw = json.loads(Path(a.places).read_text())
        items = raw.get('places', raw) if isinstance(raw, dict) else raw
        if isinstance(items, dict):
            for name, v in items.items():
                if isinstance(v, dict) and 'x' in v:
                    places[name] = (float(v['x']), float(v['y']))
        elif isinstance(items, list):
            for v in items:
                if isinstance(v, dict) and 'x' in v:
                    places[v.get('name', '?')] = (float(v['x']), float(v['y']))
    confirmed = []
    if a.virtual:
        sys.path.insert(0, str(HERE.parents[2] / 'scripts'))
        import atlas_virtual_obstacles as vo
        confirmed = vo.load_polygons(a.virtual)
    candidates = inv.candidates(places or None)
    map_changes = changes.candidates(places or None)
    for c in map_changes:
        c['name'] = c['name'].replace('Candidate', 'Map change')
    for c in candidates + map_changes:
        c['evidence']['overlaps_confirmed'] = [n for n, poly in confirmed
                                               if ioc.overlaps(c['polygon'], [list(q) for q in poly])]
    last_pose = poses.at(poses.ob_t[-1]) if poses.ob_t else None
    summary = quality.summary(grid, robot=last_pose)
    out = {'bag': str(a.bag), 'map': str(a.map_yaml), 'counts': counts, 'pose_jumps': jumps,
           'quality': {k: v for k, v in summary.items() if k != 'tiles'},
           'weak_tiles': [t for t in summary['tiles'] if t[2] == 'W'],
           'candidates': candidates, 'map_changes': map_changes}
    Path(a.out + '.json').write_text(json.dumps(out, indent=1))
    W, H, img = render(grid, quality, summary, candidates, confirmed, quality.path, map_changes)
    write_png(a.out + '.png', W, H, img)
    print(json.dumps({'counts': counts, 'pose_jumps': jumps, 'tiles': summary['counts'],
                      'verdict': summary['verdict_text'], 'candidates': len(candidates),
                      'map_changes': len(map_changes)}, indent=1))
    for c in candidates[:12] + map_changes[:12]:
        print(c['name'], c['polygon'][0], c['polygon'][2], c['evidence'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
