#!/usr/bin/env python3
"""Build a taught route from a teach_route_record.py recording (2026-11-22).

The owner's drive gives the topology (which way through the house). Because AMCL was not tight during the drive
(xy std up to ~0.6 m), narrow sections are NOT copied from the recorded poses: wherever the free width across the
travel direction (accepted map + virtual obstacles, unknown = blocked) is below --narrow-m, the waypoint is moved
to the wall-to-wall midpoint. The centreline is smoothed, resampled every --step-m, and every waypoint's footprint
(plus --margin-m) is checked against the map. Latched samples and samples with xy std above --max-std-m in WIDE
sections are dropped. Nothing is sent to the rover; it writes a route JSON for review.

  teach_route_build.py RECORDING.jsonl --map-yaml ~/project_atlas/maps/atlas_latest.yaml --out route.json \
      [--end X Y YAW_DEG]
"""
import argparse
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[2] / 'scripts'))
import atlas_lidar_availability as la            # noqa: E402  (OccGrid)
import atlas_virtual_obstacles as vo             # noqa: E402
from atlas_map_acceptance_core import map_pair_id   # noqa: E402

FOOT_X, FOOT_Y = (-0.25, 0.25), (-0.18, 0.18)


def load_map(yaml_path):
    """OccGrid from a map_server trinary YAML/PGM pair (no ROS)."""
    meta, image = {}, None
    for line in Path(yaml_path).read_text().splitlines():
        if ':' in line:
            k, v = line.split(':', 1); meta[k.strip()] = v.strip()
    image = Path(meta['image'].strip('\'"'))
    if not image.is_absolute():
        image = Path(yaml_path).parent / image
    res = float(meta['resolution'])
    origin = [float(v) for v in meta['origin'].strip('[]').split(',')]
    negate = int(meta.get('negate', '0'))
    occ_th, free_th = float(meta.get('occupied_thresh', 0.65)), float(meta.get('free_thresh', 0.25))
    raw = image.read_bytes()
    # binary PGM (P5): header = magic, width height, maxval
    parts, pos = [], 0
    while len(parts) < 4:
        while raw[pos:pos + 1].isspace(): pos += 1
        if raw[pos:pos + 1] == b'#':
            while raw[pos:pos + 1] not in (b'\n', b''): pos += 1
            continue
        start = pos
        while not raw[pos:pos + 1].isspace(): pos += 1
        parts.append(raw[start:pos])
    pos += 1
    if parts[0] != b'P5': raise ValueError('only binary PGM supported')
    w, h, maxval = int(parts[1]), int(parts[2]), int(parts[3])
    pix = raw[pos:pos + w * h]
    data = [0] * (w * h)
    for row in range(h):                 # PGM row 0 is the top; OccupancyGrid row 0 is the bottom
        for col in range(w):
            p = pix[row * w + col] / maxval
            occ = p if negate else 1.0 - p
            v = 100 if occ > occ_th else (0 if occ < free_th else -1)
            data[(h - 1 - row) * w + col] = v
    return la.OccGrid(w, h, res, origin[0], origin[1], data), image


def blocked(g, x, y):
    gx, gy = int(math.floor((x - g.ox) / g.res)), int(math.floor((y - g.oy) / g.res))
    if not (0 <= gx < g.w and 0 <= gy < g.h): return True
    v = g.data[gy * g.w + gx]
    return v >= g.occ or v < 0


def side(g, x, y, ang, max_d=1.5):
    d = 0.0
    while d < max_d:
        if blocked(g, x + d * math.cos(ang), y + d * math.sin(ang)): return d
        d += 0.01
    return max_d


def footprint_clear(g, x, y, yaw, margin):
    c, s = math.cos(yaw), math.sin(yaw)
    step = g.res / 2
    xs = [FOOT_X[0] - margin + i * step for i in range(int((FOOT_X[1] - FOOT_X[0] + 2 * margin) / step) + 1)]
    ys = [FOOT_Y[0] - margin + j * step for j in range(int((FOOT_Y[1] - FOOT_Y[0] + 2 * margin) / step) + 1)]
    for fx in xs:
        for fy in ys:
            if blocked(g, x + fx * c - fy * s, y + fx * s + fy * c):
                return False
    return True


def min_clearance(g, x, y, yaw):
    for m10 in range(0, 40):
        if not footprint_clear(g, x, y, yaw, m10 / 100.0):
            return (m10 - 1) / 100.0
    return 0.4


def nudge(g, w, target=0.12, max_off=0.35, max_dyaw_deg=20):
    """Move a waypoint sideways (perpendicular to its heading) and turn it slightly to get the most footprint
    clearance; prefers the smallest change among the best. Returns the (possibly) moved waypoint."""
    best = (min_clearance(g, w['x'], w['y'], w['yaw']), 0.0, 0.0)
    if best[0] >= target:
        return w
    for oi in range(-int(max_off / 0.02), int(max_off / 0.02) + 1):
        off = oi * 0.02
        for dy in range(-max_dyaw_deg, max_dyaw_deg + 1, 5):
            yaw = w['yaw'] + math.radians(dy)
            x = w['x'] + off * math.cos(w['yaw'] + math.pi / 2)
            y = w['y'] + off * math.sin(w['yaw'] + math.pi / 2)
            c = min_clearance(g, x, y, yaw)
            key = (round(c, 2), -abs(off) - abs(dy) / 200.0)
            if key > (round(best[0], 2), -abs(best[1]) - abs(best[2]) / 200.0):
                best = (c, off, dy)
    c, off, dy = best
    out = dict(w)
    out['x'] = round(w['x'] + off * math.cos(w['yaw'] + math.pi / 2), 3)
    out['y'] = round(w['y'] + off * math.sin(w['yaw'] + math.pi / 2), 3)
    out['yaw'] = round(w['yaw'] + math.radians(dy), 4)
    out['nudged'] = (round(off, 2), dy)
    return out


def build(rows, g, narrow_m=1.4, max_std_m=0.25, step_m=0.25, end=None):
    pts = [p for p in rows if p.get('x') is not None and not p.get('stop_latched')]
    path = [pts[0]]
    for p in pts[1:]:
        if math.hypot(p['x'] - path[-1]['x'], p['y'] - path[-1]['y']) >= 0.08:
            path.append(p)
    centre = []
    for i, p in enumerate(path):
        a, b = path[max(0, i - 1)], path[min(len(path) - 1, i + 1)]
        head = math.atan2(b['y'] - a['y'], b['x'] - a['x']) if (a is not b) else p['yaw']
        x, y = p['x'], p['y']
        l, r = side(g, x, y, head + math.pi / 2), side(g, x, y, head - math.pi / 2)
        if l + r < narrow_m:
            off = (l - r) / 2.0
            centre.append((x + off * math.cos(head + math.pi / 2), y + off * math.sin(head + math.pi / 2), 'narrow'))
        elif p.get('xy_std_m') is not None and p['xy_std_m'] <= max_std_m:
            centre.append((x, y, 'wide'))
    sm = []
    for i in range(len(centre)):
        win = centre[max(0, i - 1):i + 2]
        sm.append((sum(c[0] for c in win) / len(win), sum(c[1] for c in win) / len(win), centre[i][2]))
    out = [sm[0]]
    for c in sm[1:]:
        if math.hypot(c[0] - out[-1][0], c[1] - out[-1][1]) >= step_m:
            out.append(c)
    if end is not None:
        # cut at the centreline point nearest the end pose (drops any wandering after arrival), then add the end
        near = [i for i in range(len(out)) if math.hypot(out[i][0] - end[0], out[i][1] - end[1]) <= 0.3]
        k = near[0] if near else min(range(len(out)), key=lambda i: math.hypot(out[i][0] - end[0], out[i][1] - end[1]))
        out = out[:k + 1]
        while out and math.hypot(out[-1][0] - end[0], out[-1][1] - end[1]) < step_m:
            out.pop()
        out.append((end[0], end[1], 'end'))
    wps = []
    for i, c in enumerate(out):
        if end is not None and i == len(out) - 1:
            yaw = math.radians(end[2])
        else:   # central difference: the heading through a doorway follows the doorway axis
            a, b = out[max(0, i - 1)], out[min(len(out) - 1, i + 1)]
            yaw = math.atan2(b[1] - a[1], b[0] - a[0])
        wps.append({'x': round(c[0], 3), 'y': round(c[1], 3), 'yaw': round(yaw, 4), 'kind': c[2]})
    return wps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('recording'); ap.add_argument('--map-yaml', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--virtual', default=vo.DEFAULT_CONFIG)
    ap.add_argument('--end', nargs=3, type=float, metavar=('X', 'Y', 'YAW_DEG'))
    ap.add_argument('--narrow-m', type=float, default=1.4); ap.add_argument('--step-m', type=float, default=0.25)
    ap.add_argument('--max-std-m', type=float, default=0.25); ap.add_argument('--margin-m', type=float, default=0.05)
    a = ap.parse_args()
    raw, image = load_map(a.map_yaml)
    g = vo.overlay_grid(raw, vo.load_polygons(a.virtual))
    rows = [json.loads(l) for l in open(a.recording) if l.strip() and '"x"' in l]
    wps = [nudge(g, w) for w in build(rows, g, a.narrow_m, a.max_std_m, a.step_m, a.end)]
    bad = []
    for w in wps:
        w['clearance_m'] = min_clearance(g, w['x'], w['y'], w['yaw'])
        if w['clearance_m'] < a.margin_m:
            bad.append(w)
    dist = sum(math.hypot(b['x'] - a_['x'], b['y'] - a_['y']) for a_, b in zip(wps, wps[1:]))
    route = {'frame_id': 'map', 'map_id': map_pair_id(Path(a.map_yaml), image), 'point_count': len(wps),
             'distance_m': round(dist, 3), 'source': 'teach_route_build.py from %s' % Path(a.recording).name,
             'points': [{'x': w['x'], 'y': w['y'], 'yaw': w['yaw']} for w in wps]}
    Path(a.out).write_text(json.dumps(route, indent=1))
    for w in wps:
        print('%6.2f %6.2f %5.0f  %-6s clearance %.2f m%s%s' % (w['x'], w['y'], math.degrees(w['yaw']), w['kind'],
              w['clearance_m'], '  nudged %+.2f m %+d deg' % w['nudged'] if w.get('nudged') else '',
              '  <-- TOO CLOSE' if w in bad else ''))
    print('map_id', route['map_id'], 'points', len(wps), 'distance %.2f m' % dist, 'too close', len(bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
