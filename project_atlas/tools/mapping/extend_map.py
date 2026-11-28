#!/usr/bin/env python3
"""Offline add-only map extension (2026-11-26). No ROS; read-only on its inputs.

Aligns a new SLAM piece to the saved map and writes a CANDIDATE pair where every saved cell is unchanged and only
saved-unknown cells are filled. Never writes over the live map; promotion stays with the acceptance gate, the parked
review and the owner's OK.

  python3 tools/mapping/extend_map.py SAVED.yaml NEW.yaml OUT_PREFIX --init X Y YAW_DEG
  python3 tools/mapping/extend_map.py SAVED.yaml NEW.yaml OUT_PREFIX --wide      (unknown start: search all headings)

Writes OUT_PREFIX.json (report), OUT_PREFIX_preview.png (gray saved, green added free, dark green added walls,
red = new walls in saved free space) and, only if every check passes, OUT_PREFIX_candidate.{pgm,yaml}.
"""
import argparse
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[2] / 'scripts'))
import atlas_map_extend_core as ex  # noqa: E402
from replay_guided_mapping import write_png  # noqa: E402

LIVE_NAMES = {'atlas_latest'}


def wide_init(old, new, policy=ex.ExtendPolicy()):
    """Kept for the CLI: see atlas_map_extend_core.wide_search."""
    return ex.wide_search(old, new, policy)


def preview(result, scale=3):
    g = result['grid']
    added, conflicts = set(result['added']), set(result['conflicts'])
    W, H = g.w * scale, g.h * scale
    img = bytearray(W * H * 3)
    for gy in range(g.h):
        for gx in range(g.w):
            i = gy * g.w + gx
            v = g.data[i]
            if i in conflicts:
                col = (226, 75, 74)
            elif i in added:
                col = (59, 109, 17) if v == 100 else (192, 221, 151)
            else:
                col = (68, 68, 65) if v == 100 else ((211, 209, 199) if v == 0 else (120, 120, 120))
            for dy in range(scale):
                o = ((g.h - 1 - gy) * scale + dy) * W * 3 + gx * scale * 3
                for dx in range(scale):
                    img[o + 3 * dx:o + 3 * dx + 3] = bytes(col)
    return W, H, img


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('saved')
    ap.add_argument('new')
    ap.add_argument('out')
    ap.add_argument('--init', nargs=3, type=float, metavar=('X', 'Y', 'YAW_DEG'))
    ap.add_argument('--wide', action='store_true')
    a = ap.parse_args(argv)
    out = Path(a.out)
    if out.name in LIVE_NAMES or out.with_name(out.name + '_candidate').name in LIVE_NAMES:
        raise SystemExit('refusing to write over the live map name')
    if not a.wide and a.init is None:
        raise SystemExit('give --init X Y YAW_DEG (the localization map->odom at session start) or --wide')
    old, new = ex.read_map(a.saved), ex.read_map(a.new)
    init = wide_init(old, new) if a.wide else (a.init[0], a.init[1], math.radians(a.init[2]))
    r = ex.evaluate(old, new, init)
    report = {'saved': str(a.saved), 'new': str(a.new), 'ok': r['ok'], 'failures': r['failures'],
              'init': [round(init[0], 3), round(init[1], 3), round(math.degrees(init[2]), 1)],
              'T': [r['T'][0], r['T'][1], round(math.degrees(r['T'][2]), 2)], 'match': r['match'],
              'overlap': r['overlap'], 'stats': r['stats']}
    W, H, img = preview(r)
    write_png(str(out) + '_preview.png', W, H, img)
    if r['ok']:
        report['candidate_yaml'] = str(ex.write_map(r['grid'], Path(str(out) + '_candidate')))
    Path(str(out) + '.json').write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
    return 0 if r['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
