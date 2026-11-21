#!/usr/bin/env python3
"""How well a coloured 3D cloud agrees with the 2D LiDAR map (read-only). 2026-11-14.

Takes points between ZLO and ZHI (walls/furniture faces), drops them to 2D, and measures the distance from each to
the nearest occupied cell of the saved 2D map. A doubled wall shows up as a second peak / heavy tail.
Usage: wall_check.py CLOUD.ply MAP_PREFIX [--zlo 0.15 --zhi 1.2] [--box xmin,xmax,ymin,ymax]
"""
import argparse, math
import numpy as np
from pathlib import Path
import yaml
from scipy.spatial import cKDTree


def read_ply(p):
    with open(p, 'rb') as f:
        h = b''
        while not h.endswith(b'end_header\n'):
            h += f.readline()
        n = int([l for l in h.split(b'\n') if l.startswith(b'element vertex')][0].split()[-1])
        a = np.frombuffer(f.read(), dtype=[('x', '<f4'), ('y', '<f4'), ('z', '<f4'), ('r', 'u1'), ('g', 'u1'), ('b', 'u1')], count=n)
    return np.c_[a['x'], a['y'], a['z']]


def map_points(prefix):
    meta = yaml.safe_load(Path(prefix + '.yaml').read_text())
    raw = Path(prefix + '.pgm').read_bytes(); parts = raw.split(maxsplit=4)
    w, h = int(parts[1]), int(parts[2])
    img = np.frombuffer(parts[4][-w * h:], dtype=np.uint8).reshape(h, w)
    rows, cols = np.nonzero(img < 50)
    res, ox, oy = meta['resolution'], meta['origin'][0], meta['origin'][1]
    return np.c_[ox + (cols + 0.5) * res, oy + (h - 1 - rows + 0.5) * res]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cloud'); ap.add_argument('map')
    ap.add_argument('--zlo', type=float, default=0.15); ap.add_argument('--zhi', type=float, default=1.2)
    ap.add_argument('--box')
    a = ap.parse_args()
    P = read_ply(a.cloud)
    P = P[(P[:, 2] > a.zlo) & (P[:, 2] < a.zhi)]
    if a.box:
        x0, x1, y0, y1 = map(float, a.box.split(','))
        P = P[(P[:, 0] > x0) & (P[:, 0] < x1) & (P[:, 1] > y0) & (P[:, 1] < y1)]
    d, _ = cKDTree(map_points(a.map)).query(P[:, :2])
    near = d < 0.6                     # ignore furniture far from any mapped wall
    dn = d[near]
    print(f'{Path(a.cloud).name}{" box " + a.box if a.box else ""}: {len(P)} pts, near-wall {near.mean()*100:.0f}% | '
          f'median {np.median(dn)*100:.1f} cm, p75 {np.percentile(dn, 75)*100:.1f}, p90 {np.percentile(dn, 90)*100:.1f} cm | '
          f'within 5 cm {(dn < 0.05).mean()*100:.0f}%, 10-30 cm {((dn > 0.10) & (dn < 0.30)).mean()*100:.0f}%')


if __name__ == '__main__':
    main()
