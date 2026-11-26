#!/usr/bin/env python3
"""Extend job (2026-11-26; design docs/design/guided_mapping_assistant.md section 10). No ROS.

After an extend session, mission control writes <state>/<session>.request.json and never promotes anything. This job
turns each pending request into <state>/<session>/{result.json, preview.png} and, ONLY if every check passes,
candidate.{pgm,yaml}; <state>/latest.json points the dashboard at the newest result. It never writes the saved map:
promotion stays a separate, owner-approved step (parked, E-STOP latched) through the existing backup + transactional
promotion. It waits while any mapping session is active and runs at low priority (unit: Nice 19, CPUQuota 40 %).
"""
import json
import math
import os
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
import atlas_map_extend_core as ex  # noqa: E402
from atlas_map_acceptance_core import map_pair_id  # noqa: E402

STATE_DIR = Path.home() / '.local/state/project_atlas/map_extend'
SAVED_YAML = Path('/home/jetson/project_atlas/maps/atlas_latest.yaml')
SESSION_FILE = Path.home() / '.config/project_atlas/mapping_session.json'
PERIOD_S = 15.0


def _atomic_json(path, value):
    tmp = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    tmp.write_text(json.dumps(value, indent=1), encoding='utf-8')
    os.replace(tmp, path)


def _image_of(yaml_path):
    for line in Path(yaml_path).read_text(encoding='utf-8').splitlines():
        if line.strip().startswith('image:'):
            name = line.split(':', 1)[1].strip().strip('\'"')
            p = Path(name)
            return p if p.is_absolute() else Path(yaml_path).parent / p
    raise ValueError('map YAML has no image')


def _preview_png(path, result, scale=3):
    g, added, conflicts = result['grid'], set(result['added']), set(result['conflicts'])
    W, H = g.w * scale, g.h * scale
    rows = []
    import zlib
    import struct
    for row in range(g.h):
        gy = g.h - 1 - row
        line = bytearray()
        for gx in range(g.w):
            i = gy * g.w + gx
            v = g.data[i]
            if i in conflicts:
                col = (226, 75, 74)
            elif i in added:
                col = (59, 109, 17) if v == 100 else (192, 221, 151)
            else:
                col = (68, 68, 65) if v == 100 else ((211, 209, 199) if v == 0 else (120, 120, 120))
            line += bytes(col) * scale
        rows.extend([b'\x00' + bytes(line)] * scale)

    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0))
                           + chunk(b'IDAT', zlib.compress(b''.join(rows), 9)) + chunk(b'IEND', b''))


def _end_pose_saved(T, end):
    if not isinstance(end, dict) or 'x' not in end:
        return None
    c, s = math.cos(T[2]), math.sin(T[2])
    x, y = float(end['x']), float(end['y'])
    return {'frame_id': 'map', 'x': round(T[0] + c * x - s * y, 3), 'y': round(T[1] + s * x + c * y, 3)}


def process_one(req, state_dir, saved_yaml):
    sid = req['session_id']
    out = Path(state_dir) / sid
    out.mkdir(parents=True, exist_ok=True)
    result = {'schema': 1, 'session_id': sid, 'created_unix': time.time(), 'ok': False, 'failures': [],
              'used_wide_search': False, 'preview': None, 'candidate_yaml': None}
    try:
        current_id = map_pair_id(saved_yaml, _image_of(saved_yaml))
        if req.get('base_map_id') and current_id != req['base_map_id']:
            result['failures'].append('the saved map changed since this session started; drive the extension again')
            return result
        old = ex.read_map(saved_yaml)
        try:
            new = ex.read_map(req['candidate_yaml'])
        except (OSError, ValueError, KeyError) as exc:
            result['failures'].append(f'could not read the new map piece: {exc}')
            return result
        init = tuple(req.get('init') or (0.0, 0.0, 0.0))
        r = ex.evaluate(old, new, init)
        if not r['ok'] and any('does not line up' in f for f in r['failures']):
            r2 = ex.evaluate(old, new, ex.wide_search(old, new))
            result['used_wide_search'] = True
            if r2['ok'] or r2['match'] > r['match']:
                r = r2
        _preview_png(out / 'preview.png', r)
        result.update(ok=r['ok'], failures=r['failures'], T=[r['T'][0], r['T'][1], round(math.degrees(r['T'][2]), 2)],
                      match=r['match'], overlap=r['overlap'], stats=r['stats'], preview=str(out / 'preview.png'),
                      end_pose_saved=_end_pose_saved(r['T'], req.get('end_pose_slam')), base_map_id=current_id)
        if r['ok']:
            result['candidate_yaml'] = str(ex.write_map(r['grid'], out / 'candidate'))
        return result
    finally:
        _atomic_json(out / 'result.json', result)
        _atomic_json(Path(state_dir) / 'latest.json', result)


def process_pending(state_dir=STATE_DIR, saved_yaml=SAVED_YAML, session_file=SESSION_FILE):
    """Handle every pending request (oldest first). Does nothing while a mapping session is active."""
    state_dir = Path(state_dir)
    if Path(session_file).exists() or not state_dir.is_dir():
        return []
    results = []
    for p in sorted(state_dir.glob('*.request.json'), key=lambda q: q.stat().st_mtime):
        try:
            req = json.loads(p.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if req.get('state') != 'pending' or not req.get('session_id'):
            continue
        results.append(process_one(req, state_dir, saved_yaml))
        req['state'] = 'done'
        _atomic_json(p, req)
    return results


def main():
    while True:
        try:
            for r in process_pending():
                print(f"extend {r['session_id'][:8]}: ok={r['ok']} {'; '.join(r['failures'])}", flush=True)
        except Exception as exc:                                # noqa: BLE001 - keep the loop alive, report
            print(f'extend job error: {exc}', flush=True)
        time.sleep(PERIOD_S)


if __name__ == '__main__':
    main()
