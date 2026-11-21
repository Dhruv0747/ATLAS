#!/usr/bin/env python3
"""Stage 1 browser evidence: E-STOP input handling in V1 (before/after fix) and V2, offline.

Headless Chromium with real CDP multi-touch on a phone viewport; every POST is captured by the
harness and never sent. Usage: test_estop_browser.py <snap_old_v1> <snap_fixed_v1> <out.json>
  snap_old_v1   recorded live snapshot (current V1, before the fix)
  snap_fixed_v1 same snapshot with index.html rendered from the patched source
"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Harness, open_page
from playwright.sync_api import sync_playwright

OLD, FIX, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
PHONE = ((390, 844), 3)
FWD, CAM_UP = '[data-l=".65"][data-a="0"]', '[data-cam="tilt"][data-dir="1"], [data-cam][data-dir="1"]'
R, FAIL = {}, []


def center(pg, sel):
    return pg.evaluate('s => { const e = document.querySelector(s); e.scrollIntoView({block:"center"}); '
                       'const r = e.getBoundingClientRect(); return [r.x + r.width/2, r.y + r.height/2]; }', sel)


def touch(cdp, kind, pts):
    cdp.send('Input.dispatchTouchEvent', {'type': kind, 'touchPoints': [{'x': x, 'y': y, 'id': i} for i, (x, y) in pts]})


def bodies(h, since=0):
    return [p['body'] or '' for p in h.posts[since:]]


def scenario_two_finger(b, snap, path, hold_sel, stop_sel, kind):
    """Finger 0 holds `hold_sel`; finger 1 taps `stop_sel`; finger 0 stays down 1.5 s more."""
    h = Harness(snap); ctx, pg = open_page(b, h, path, *PHONE); pg.wait_for_timeout(1500)
    cdp = ctx.new_cdp_session(pg)
    f = center(pg, hold_sel); s = pg.evaluate('s => { const r = document.querySelector(s).getBoundingClientRect(); return [r.x+r.width/2, r.y+r.height/2]; }', stop_sel)
    h.posts.clear()
    touch(cdp, 'touchStart', [(0, f)]); pg.wait_for_timeout(500)
    before = bodies(h)
    touch(cdp, 'touchStart', [(0, f), (1, s)]); pg.wait_for_timeout(60)
    touch(cdp, 'touchEnd', [(0, f)]); t_stop = len(h.posts); pg.wait_for_timeout(1500)
    after = bodies(h, t_stop)
    timers = pg.evaluate('() => ({hold: typeof hold === "undefined" ? "n/a" : hold, cameraHold: typeof cameraHold === "undefined" ? "n/a" : cameraHold})')
    touch(cdp, 'touchEnd', [])
    pg.wait_for_timeout(300); ctx.close()
    seq = bodies(h)
    estop_i = next((i for i, x in enumerate(seq) if x == 'action=e_stop'), None)
    moving = [x for x in (seq[estop_i + 1:] if estop_i is not None else after) if x.startswith('action=' + kind)]
    return {'repeat_before_estop': sum(x.startswith('action=' + kind) for x in before),
            'e_stop_sent': estop_i is not None, 'e_stop_count': seq.count('action=e_stop'),
            f'{kind}_posts_after_e_stop_while_held': len(moving), 'timers_after': timers,
            'sequence': [x for i, x in enumerate(seq) if i == 0 or x != seq[i - 1]]}


def scenario_input(b, snap, path, how):
    h = Harness(snap); ctx, pg = open_page(b, h, path, *PHONE if how == 'touch_tap' else ((1440, 900), 1)); pg.wait_for_timeout(1500)
    h.posts.clear()
    if how == 'mouse_click':
        pg.click('#stop'); pg.wait_for_timeout(400)
    elif how == 'keyboard_enter':
        pg.focus('#stop'); pg.keyboard.press('Enter'); pg.wait_for_timeout(400)
    elif how == 'keyboard_space':
        pg.focus('#stop'); pg.keyboard.press('Space'); pg.wait_for_timeout(400)
    elif how == 'touch_tap':
        pg.tap('#stop'); pg.wait_for_timeout(400)
    n = bodies(h).count('action=e_stop'); ctx.close()
    return n


with sync_playwright() as p:
    b = p.chromium.launch()
    for label, snap, path in (('v1_before_fix', OLD, '/'), ('v1_fixed', FIX, '/'), ('v2', FIX, '/v2/')):
        out = {}
        out['two_finger_drive_pad_estop'] = scenario_two_finger(b, snap, path, FWD, '#stop', 'drive')
        if label == 'v2':
            out['two_finger_drive_dock_estop'] = scenario_two_finger(b, snap, path, FWD, '#v2Estop', 'drive')
        cam = 'button[data-cam]:not([data-cam="center"])'
        out['two_finger_camera_hold_estop'] = scenario_two_finger(b, snap, path, cam, '#stop', 'camera')
        for how in ('mouse_click', 'keyboard_enter', 'keyboard_space', 'touch_tap'):
            out[f'e_stop_count_{how}'] = scenario_input(b, snap, path, how)
        R[label] = out
        print(label, json.dumps(out))
    b.close()

for label in ('v1_fixed', 'v2'):
    o = R[label]
    for k in [k for k in o if k.startswith('two_finger')]:
        v = o[k]
        if not v['e_stop_sent']: FAIL.append(f'{label} {k}: no e_stop')
        if v['e_stop_count'] != 1: FAIL.append(f'{label} {k}: e_stop sent {v["e_stop_count"]} times')
        if any(n for kk, n in v.items() if kk.endswith('_after_e_stop_while_held')): FAIL.append(f'{label} {k}: motion/camera repeat continued')
        if v['timers_after']['hold'] not in (None, 'n/a') or v['timers_after']['cameraHold'] not in (None, 'n/a'):
            FAIL.append(f'{label} {k}: timer still set {v["timers_after"]}')
        if v['repeat_before_estop'] < 2: FAIL.append(f'{label} {k}: hold did not start (test invalid)')
    for how in ('mouse_click', 'keyboard_enter', 'keyboard_space', 'touch_tap'):
        if o[f'e_stop_count_{how}'] != 1: FAIL.append(f'{label} {how}: e_stop count {o[f"e_stop_count_{how}"]}')
R['failures'] = FAIL
Path(OUT).write_text(json.dumps(R, indent=1))
print('FAILURES', len(FAIL)); [print(' -', f) for f in FAIL]
sys.exit(1 if FAIL else 0)
