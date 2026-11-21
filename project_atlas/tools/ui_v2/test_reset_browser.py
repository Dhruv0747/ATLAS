#!/usr/bin/env python3
"""Stage 1b browser evidence: E-STOP reset panel in V1 and V2 (display + request only; the server decides).

Usage: test_reset_browser.py <snap_dir_with_v1_render> <out_dir>
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Harness, open_page
from playwright.sync_api import sync_playwright

SNAP, OUT = sys.argv[1], Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
PHONE = ((390, 844), 3)
FAIL, R = [], {}
STATES = {
    'available': {'latched': True, 'reason': 'REMOTE STOP: voice stop requested', 'drive_requires_fresh_press': False,
                  'reset': {'available': True, 'blocked': [], 'challenge': 'nonce-abc', 'challenge_ttl_s': 10, 'pin_configured': True, 'lockout_s': 0}},
    'blocked': {'latched': True, 'reason': 'REMOTE STOP: joystick unavailable', 'drive_requires_fresh_press': False,
                'reset': {'available': False, 'blocked': ['physical remote not connected', 'motion state unknown (odometry stale)'],
                          'challenge': None, 'challenge_ttl_s': 10, 'pin_configured': True, 'lockout_s': 0}},
    'released_fresh_press': {'latched': False, 'reason': 'REMOTE STOP: released by operator', 'drive_requires_fresh_press': True,
                             'reset': {'available': False, 'blocked': ['not latched'], 'challenge': None, 'challenge_ttl_s': 10, 'pin_configured': True, 'lockout_s': 0}},
}


def page(b, path, state, offline=False):
    h = Harness(SNAP)
    h.mutate(lambda d: d.__setitem__('estop', STATES[state]))
    ctx, pg = open_page(b, h, path, *PHONE)
    if offline: h.offline = True
    pg.wait_for_timeout(2200)
    return h, ctx, pg


with sync_playwright() as p:
    b = p.chromium.launch()
    for label, path in (('v1', '/'), ('v2', '/v2/')):
        out = {}
        for state in ('available', 'blocked', 'released_fresh_press'):
            h, ctx, pg = page(b, path, state)
            out[state] = pg.evaluate('() => ({text: estopState.textContent, cls: estopState.className, why: estopWhy.textContent, disabled: estopReset.disabled})')
            pg.locator('#estopResetPanel').scroll_into_view_if_needed(); pg.wait_for_timeout(200)
            pg.locator('#estopResetPanel').screenshot(path=str(OUT / f'{label}_{state}.png')); ctx.close()
        h, ctx, pg = page(b, path, 'blocked', offline=True)
        pg.wait_for_timeout(1500)
        out['connection_lost'] = pg.evaluate('() => ({text: estopState.textContent, disabled: estopReset.disabled})')
        pg.locator('#estopResetPanel').screenshot(path=str(OUT / f'{label}_connection_lost.png')); ctx.close()
        # dismissed confirmation: no request
        h, ctx, pg = page(b, path, 'available'); pg.on('dialog', lambda d: d.dismiss())
        pg.fill('#estopPin', '482913'); h.posts.clear(); pg.click('#estopReset'); pg.wait_for_timeout(500)
        out['dismissed_posts'] = [x['path'] for x in h.posts if x['path'] == '/api/estop/reset']; ctx.close()
        # accepted confirmation: exact request; a held drive is cancelled first
        h, ctx, pg = page(b, path, 'available'); dialogs = []
        pg.on('dialog', lambda d: (dialogs.append(d.message), d.accept()))
        fwd = pg.locator('[data-l=".65"][data-a="0"]'); fwd.scroll_into_view_if_needed(); bx = fwd.bounding_box()
        pg.mouse.move(bx['x'] + bx['width'] / 2, bx['y'] + bx['height'] / 2); pg.mouse.down(); pg.wait_for_timeout(400)
        pg.fill('#estopPin', '482913'); pg.evaluate('() => estopReset.click()'); pg.wait_for_timeout(800)
        posts = [x for x in h.posts]
        reset = [x for x in posts if x['path'] == '/api/estop/reset']
        i = posts.index(reset[0]) if reset else None
        out['accepted'] = {'dialog': dialogs[:1], 'reset_requests': len(reset),
                           'body': json.loads(reset[0]['body']) if reset else None, 'headers': reset[0]['headers'] if reset else None,
                           'drive_posts_after_reset_click': sum('action=drive' in (x['body'] or '') for x in posts[i + 1:]) if i is not None else None,
                           'pin_cleared': pg.evaluate('() => estopPin.value') == ''}
        pg.mouse.up(); ctx.close()
        R[label] = out; print(label, json.dumps(out))
        a = out['accepted']
        if out['available']['disabled'] or 'RESET AVAILABLE' not in out['available']['text'].upper(): FAIL.append(f'{label}: available state')
        if not out['blocked']['disabled'] or 'RESET BLOCKED' not in out['blocked']['text'].upper() or 'physical remote' not in out['blocked']['why']: FAIL.append(f'{label}: blocked state')
        if not out['connection_lost']['disabled'] or 'RESET BLOCKED' not in out['connection_lost']['text'].upper(): FAIL.append(f'{label}: connection lost state')
        if 'PRESS AGAIN' not in out['released_fresh_press']['text'].upper(): FAIL.append(f'{label}: fresh-press hint')
        if out['dismissed_posts']: FAIL.append(f'{label}: request sent although confirmation was dismissed')
        if a['reset_requests'] != 1 or a['body'] != {'nonce': 'nonce-abc', 'pin': '482913', 'confirm': 'RESET_ESTOP'}: FAIL.append(f'{label}: reset request {a}')
        if (a['headers'] or {}).get('x-atlas-wifi') != '1' or 'application/json' not in (a['headers'] or {}).get('content-type', ''): FAIL.append(f'{label}: headers {a["headers"]}')
        if a['drive_posts_after_reset_click']: FAIL.append(f'{label}: drive continued after reset click')
        if not a['pin_cleared']: FAIL.append(f'{label}: PIN field not cleared')
        if not a['dialog'] or 'will NOT move' not in a['dialog'][0]: FAIL.append(f'{label}: confirmation text')
    b.close()
R['failures'] = FAIL; (OUT / 'reset_browser.json').write_text(json.dumps(R, indent=1))
print('FAILURES', len(FAIL)); [print(' -', f) for f in FAIL]
sys.exit(1 if FAIL else 0)
