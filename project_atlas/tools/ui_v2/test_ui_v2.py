#!/usr/bin/env python3
"""Offline feature-preservation tests: ATLAS V1 dashboard vs Glass UI V2.

Runs both UIs in headless Chromium against recorded ATLAS responses (see harness.py). Every POST
is captured by the harness and answered locally; nothing reaches a rover.
Usage: test_ui_v2.py <snapshot_dir> <out_dir> [sections]   sections: comma list of ids,contracts,safety,perf,gallery
Writes <out_dir>/results.json and state-gallery screenshots. Exit code 1 if any contract test fails.
"""
import json, statistics, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Harness, open_page
from playwright.sync_api import sync_playwright

SNAP, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
PHONE, TABLET, DESKTOP = ((390, 844), 3), ((1194, 834), 2), ((1440, 900), 1)
SECTIONS = set((sys.argv[3] if len(sys.argv) > 3 else 'ids,contracts,safety,perf,gallery').split(','))
RES = OUT / 'results.json'
R = json.loads(RES.read_text()) if RES.exists() and len(sys.argv) > 3 else {}
for k, v in (('contracts', {}), ('ids', {}), ('links', {}), ('safety', {}), ('perf', {}), ('gallery', []), ('failures', [])):
    R.setdefault(k, v)



def sanitize(d):  # never put real SSIDs or addresses into screenshots or reports
    w = d['wifi']
    for i, s in enumerate(w['saved']): s['ssid'] = f'Saved network {i + 1}'
    w['job']['message'] = 'Connected (names hidden)'
    w['dashboard_urls'] = ['http://<atlas-lan-ip>:8088/']
    w['local_name_url'], w['tailscale_url'] = 'http://<atlas-name>.local:8088/', 'http://<tailscale-ip>:8088/'


def H():
    h = Harness(SNAP); h.mutate(sanitize); return h


KEY_JS = '''() => {
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  document.querySelectorAll('details').forEach(d => d.open = true);
  window.__tk = {}; const out = [];
  for (const e of document.querySelectorAll('button')) {
    if (!vis(e) || e.closest('#sensorModal')) continue;
    const data = ['l','a','cam','dir','track','ai','page'].filter(k => e.dataset[k] != null).map(k => k + '=' + e.dataset[k]).join('&');
    let k = e.id ? '#' + e.id : data ? '[' + data + ']' : e.getAttribute('onclick') ? 'onclick=' + e.getAttribute('onclick')
          : 'text=' + e.textContent.replace(/[^A-Za-z0-9]+/g, ' ').trim().toUpperCase();
    if (window.__tk[k]) k += '#2';
    window.__tk[k] = e; out.push({k, disabled: e.disabled});
  }
  return out; }'''
import re as _re
# Per-page-load random values (the commissioning steering lease session id) are masked before comparing.
_SESSION = _re.compile(r'("session":")[0-9a-f]{16,64}(")')
NORM = lambda posts: [(p['path'], _SESSION.sub(r'\1<random>\2', p['body'] or ''), p['headers'].get('content-type', ''),
                       p['headers'].get('x-atlas-wifi', '')) for p in posts]


def dedupe(seq):
    out = []
    for x in seq:
        if not out or out[-1] != x: out.append(x)
    return out


def press(pg, key, hold_ms=450):
    box = pg.evaluate('k => { const e = window.__tk[k]; if (!e) return null; e.scrollIntoView({block:"center"});'
                      ' const r = e.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }', key)
    if not box: return False
    hit = pg.evaluate('([k,x,y]) => { const t = document.elementFromPoint(x,y); return !!t && window.__tk[k].contains(t); }', [key, *box])
    if not hit:  # covered (e.g. by the dock); fall back to a DOM click so the contract is still compared
        pg.evaluate('k => window.__tk[k].click()', key); pg.wait_for_timeout(hold_ms + 350); return 'dom-click'
    pg.mouse.move(*box); pg.mouse.down(); pg.wait_for_timeout(hold_ms); pg.mouse.up(); pg.wait_for_timeout(350)
    return True


def run_button(browser, path, key, dialog_mode, vp):
    h = H(); dialogs = []
    ctx, pg = open_page(browser, h, path, *vp)
    pg.on('dialog', lambda d: (dialogs.append(d.message), d.accept() if dialog_mode == 'accept' else d.dismiss()))
    pg.wait_for_timeout(1200); pg.evaluate(KEY_JS); h.posts.clear()
    how = press(pg, key)
    res = {'posts': dedupe(NORM(h.posts)), 'dialogs': dialogs, 'how': how, 'errors': pg.errors[:3]}
    ctx.close(); return res


def contract_suite(browser, name, v1, v2, vp=DESKTOP):
    def keys(path):
        h = H(); ctx, pg = open_page(browser, h, path, *vp); pg.wait_for_timeout(1200); k = pg.evaluate(KEY_JS); ctx.close(); return k
    k1, k2 = keys(v1), keys(v2)
    s2 = {x['k'] for x in k2}
    rows = []
    for item in k1:
        k = item['k']
        row = {'control': k, 'in_v2': k in s2}
        if not row['in_v2']:
            row['ok'] = False; rows.append(row); R['failures'].append(f'{name}: {k} missing in V2'); continue
        a = run_button(browser, v1, k, 'dismiss', vp); b = run_button(browser, v2, k, 'dismiss', vp)
        row.update(v1=a['posts'], v2=b['posts'], dialog=a['dialogs'], how=[a['how'], b['how']])
        ok = a['posts'] == b['posts'] and a['dialogs'] == b['dialogs']
        if a['dialogs']:  # confirm dialogs: also compare the accepted path
            a2 = run_button(browser, v1, k, 'accept', vp); b2 = run_button(browser, v2, k, 'accept', vp)
            row.update(v1_accept=a2['posts'], v2_accept=b2['posts']); ok = ok and a2['posts'] == b2['posts']
        row['ok'] = ok
        if not ok: R['failures'].append(f'{name}: {k} request contract differs')
        rows.append(row)
    R['contracts'][name] = {'v1_controls': len(k1), 'v2_controls': len(k2), 'v2_only': sorted(s2 - {x['k'] for x in k1}), 'rows': rows}
    print(name, 'controls', len(k1), 'ok', sum(r.get('ok', False) for r in rows), 'v2-only', R['contracts'][name]['v2_only'])


def ids_and_links(browser, name, v1, v2):
    js = '''() => { document.querySelectorAll('details').forEach(d => d.open = true);
      return {ids: [...document.querySelectorAll('[id]')].map(e => e.id),
              links: [...document.querySelectorAll('a[href]')].map(a => a.getAttribute('href'))}; }'''
    got = {}
    for tag, path in (('v1', v1), ('v2', v2)):
        h = H(); ctx, pg = open_page(browser, h, path, *DESKTOP); pg.wait_for_timeout(2500); got[tag] = pg.evaluate(js); ctx.close()
    missing = sorted(set(got['v1']['ids']) - set(got['v2']['ids']))
    norm = lambda u: u.replace('/v2/', '/', 1) if u.startswith('/v2/') else u
    lmiss = sorted({norm(u) for u in got['v1']['links']} - {norm(u) for u in got['v2']['links']} - {'/'})
    R['ids'][name] = {'v1': len(set(got['v1']['ids'])), 'v2': len(set(got['v2']['ids'])), 'missing_in_v2': missing}
    R['links'][name] = {'v1': sorted(set(got['v1']['links'])), 'v2': sorted(set(got['v2']['links'])), 'missing_in_v2': lmiss}
    for m in missing: R['failures'].append(f'{name}: id #{m} missing in V2')
    for m in lmiss: R['failures'].append(f'{name}: link {m} missing in V2')
    print(name, 'ids', R['ids'][name]['v1'], '->', R['ids'][name]['v2'], 'missing', missing, 'links missing', lmiss)


def safety(browser):
    FWD = '[l=.65&a=0]'
    for tag, path in (('v1', '/'), ('v2', '/v2/')):
        out = {}
        for vp_name, vp in (('desktop', DESKTOP), ('phone', PHONE)):
            # 1. repeat cadence while held
            h = H(); ctx, pg = open_page(browser, h, path, *vp); pg.wait_for_timeout(1200); pg.evaluate(KEY_JS); h.posts.clear()
            press(pg, FWD, hold_ms=1500)
            ts = [p['t'] for p in h.posts if 'action=drive' in (p['body'] or '')]
            gaps = [round((b - a) * 1000) for a, b in zip(ts, ts[1:])]
            last = h.posts[-1]['body'] if h.posts else None
            out[f'{vp_name}_hold'] = {'drive_posts': len(ts), 'median_gap_ms': statistics.median(gaps) if gaps else None,
                                      'last_post': last, 'stop_on_release': last == 'action=stop'}
            ctx.close()
        # 2. release paths with the pointer still physically down
        for ev, js in (('pointercancel', "k => window.__tk[k].dispatchEvent(new PointerEvent('pointercancel',{pointerId:1,bubbles:true}))"),
                       ('window_blur', "() => window.dispatchEvent(new Event('blur'))"),
                       ('page_hidden', "() => { Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});"
                                       " Object.defineProperty(document,'visibilityState',{configurable:true,get:()=>'hidden'});"
                                       " document.dispatchEvent(new Event('visibilitychange')); }")):
            h = H(); ctx, pg = open_page(browser, h, path, *DESKTOP); pg.wait_for_timeout(1200); pg.evaluate(KEY_JS)
            box = pg.evaluate('k => { const e = window.__tk[k]; e.scrollIntoView({block:"center"}); const r = e.getBoundingClientRect(); return [r.x+r.width/2, r.y+r.height/2]; }', FWD)
            h.posts.clear(); pg.mouse.move(*box); pg.mouse.down(); pg.wait_for_timeout(400)
            pg.evaluate(js, FWD) if 'k =>' in js else pg.evaluate(js); t_ev = time.time(); pg.wait_for_timeout(700)
            after = [p['body'] for p in h.posts if p['t'] > t_ev + 0.05]
            stops = [p for p in h.posts if p['body'] == 'action=stop']
            out[ev] = {'stop_sent': bool(stops), 'drive_posts_after_event': sum('action=drive' in (b or '') for b in after)}
            pg.mouse.up(); ctx.close()
        # 3. E-STOP pressed (second pointer) while a drive button is still held. V1: recorded (known hazard). V2: must send 0 drive after e_stop
        for btn in (['#stop'] + (['#v2Estop'] if tag == 'v2' else [])):
            h = H(); ctx, pg = open_page(browser, h, path, *DESKTOP); pg.wait_for_timeout(1200); pg.evaluate(KEY_JS)
            box = pg.evaluate('k => { const e = window.__tk[k]; e.scrollIntoView({block:"center"}); const r = e.getBoundingClientRect(); return [r.x+r.width/2, r.y+r.height/2]; }', FWD)
            h.posts.clear(); pg.mouse.move(*box); pg.mouse.down(); pg.wait_for_timeout(400)
            pg.evaluate(f'() => document.querySelector("{btn}").click()'); pg.wait_for_timeout(800)
            bodies = [p['body'] for p in h.posts]
            i = bodies.index('action=e_stop') if 'action=e_stop' in bodies else None
            out[f'estop_while_holding{btn}'] = {'e_stop_body': bodies[i] if i is not None else None,
                                                'drive_posts_after_e_stop': sum('action=drive' in (b or '') for b in bodies[i + 1:]) if i is not None else None}
            pg.mouse.up(); ctx.close()
        # 4. Real two-finger touch (CDP touch points, phone viewport): finger 1 holds Forward, finger 2 taps the
        #    drive-pad E-STOP; finger 1 stays down 0.8 s, then lifts; then a fresh single press must drive again.
        for btn in (['#stop'] + (['#v2Estop'] if tag == 'v2' else [])):
            h = H(); ctx, pg = open_page(browser, h, path, *PHONE); pg.wait_for_timeout(1200); pg.evaluate(KEY_JS)
            cdp = ctx.new_cdp_session(pg)
            f = pg.evaluate('k => { const e = window.__tk[k]; e.scrollIntoView({block:"center"}); const r = e.getBoundingClientRect(); return [r.x+r.width/2, r.y+r.height/2]; }', FWD)
            sb = pg.evaluate('b => { const r = document.querySelector(b).getBoundingClientRect(); return [r.x+r.width/2, r.y+r.height/2]; }', btn)
            tp = lambda pts: [{'x': x, 'y': y, 'id': i} for i, (x, y) in pts]
            h.posts.clear()
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': tp([(0, f)])}); pg.wait_for_timeout(400)
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': tp([(0, f), (1, sb)])}); pg.wait_for_timeout(60)
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': tp([(0, f)])}); pg.wait_for_timeout(800)
            bodies = [p['body'] for p in h.posts]; i = bodies.index('action=e_stop') if 'action=e_stop' in bodies else None
            held = sum('action=drive' in (b or '') for b in bodies[i + 1:]) if i is not None else None
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []}); pg.wait_for_timeout(300)
            n0 = len(h.posts)
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': tp([(2, f)])}); pg.wait_for_timeout(400)
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []}); pg.wait_for_timeout(300)
            fresh = [p['body'] for p in h.posts[n0:]]
            out['two_finger_touch_estop' + ('' if btn == '#stop' else btn)] = {'e_stop_sent': i is not None, 'drive_posts_after_e_stop_while_finger_down': held,
                                             'fresh_press_after_lift_drives': any('action=drive' in (b or '') for b in fresh),
                                             'fresh_press_ends_with_stop': bool(fresh) and fresh[-1] == 'action=stop'}
            ctx.close()
        R['safety'][tag] = out
    v1, v2 = R['safety']['v1'], R['safety']['v2']
    for k in ('estop_while_holding#stop', 'estop_while_holding#v2Estop'):
        if v2[k]['drive_posts_after_e_stop'] != 0: R['failures'].append(f'safety: V2 {k} still sent drive after e_stop')
    for key in ('two_finger_touch_estop', 'two_finger_touch_estop#v2Estop'):
        t2 = v2[key]
        if not t2['e_stop_sent'] or t2['drive_posts_after_e_stop_while_finger_down'] != 0:
            R['failures'].append(f'safety: V2 {key} {t2}')
        if not (t2['fresh_press_after_lift_drives'] and t2['fresh_press_ends_with_stop']):
            R['failures'].append(f'safety: V2 drive pad did not recover for a fresh press after lift {key} {t2}')
    for k in ('desktop_hold', 'phone_hold'):
        if not v2[k]['stop_on_release']: R['failures'].append(f'safety: {k} release did not send stop in V2')
    for ev in ('pointercancel', 'window_blur', 'page_hidden'):
        if v1[ev] != v2[ev]: R['failures'].append(f'safety: {ev} behaviour differs v1={v1[ev]} v2={v2[ev]}')
    if v2['estop_while_holding#v2Estop']['e_stop_body'] != v1['estop_while_holding#stop']['e_stop_body']:
        R['failures'].append('safety: dock E-STOP body differs from drive-pad E-STOP')
    print('safety', json.dumps(R['safety'])[:900])


def perf(browser):
    for vp_name, vp in (('phone', PHONE), ('desktop', DESKTOP)):
        for tag, path in (('v1', '/'), ('v2', '/v2/')):
            for where in ('top', 'scrolled_to_bottom'):
                h = H(); ctx, pg = open_page(browser, h, path, *vp)
                cdp = ctx.new_cdp_session(pg); cdp.send('Performance.enable'); pg.wait_for_timeout(1500)
                if where != 'top': pg.evaluate('window.scrollTo(0, document.body.scrollHeight)'); pg.wait_for_timeout(300)
                m0 = {m['name']: m['value'] for m in cdp.send('Performance.getMetrics')['metrics']}; h.counts.clear()
                pg.wait_for_timeout(10000)
                m1 = {m['name']: m['value'] for m in cdp.send('Performance.getMetrics')['metrics']}
                R['perf'][f'{vp_name}/{tag}/{where}'] = {
                    'dom_nodes': int(m1['Nodes']), 'script_ms_per_s': round((m1['ScriptDuration'] - m0['ScriptDuration']) * 100, 2),
                    'layout_ms_per_s': round((m1['LayoutDuration'] - m0['LayoutDuration']) * 100, 2), 'heap_mb': round(m1['JSHeapUsedSize'] / 1e6, 2),
                    'camera_req_10s': h.counts.get('/camera.jpg', 0), 'radar_req_10s': h.counts.get('/api/radar', 0),
                    'status_req_10s': h.counts.get('/api/status', 0), 'map_req_10s': h.counts.get('/api/map', 0)}
                ctx.close()
    for k, v in R['perf'].items(): print('perf', k, v)


STATES = {
    'verified_stopped': lambda d: d['map']['localization_check']['value'].update(state='VERIFIED', check_age_s=6.0, reason='LiDAR scan matches the map (fit 0.98)'),
    'degraded': lambda d: None,  # the recorded live sample
    'lost': lambda d: d['map']['localization_check']['value'].update(state='LOST', reason='LiDAR disagrees with AMCL by 0.9 m'),
    'moving': lambda d: (d['map']['localization_check']['value'].update(state='MOVING_UNVERIFIED', reason='Rover moving; LiDAR check paused'),
                         d['status']['ros']['odom']['value'].update(vx=0.12, wz=0.05)),
    'connection_delayed': lambda d: None,
}


def gallery(browser):
    R['gallery'] = []
    for state, fn in STATES.items():
        for page, path, vp, clip in (('command', '/v2/', PHONE, None), ('mapping', '/v2/mapping', DESKTOP, None)):
            h = H(); h.mutate(fn); ctx, pg = open_page(browser, h, path, *vp); pg.wait_for_timeout(3000)
            if state == 'connection_delayed': h.offline = True; pg.wait_for_timeout(7000)
            shot = OUT / f'state_{state}_{page}.png'
            pg.screenshot(path=str(shot))
            chips = pg.evaluate('() => [...document.querySelectorAll(".chip:not([hidden]), #liveState")].map(e => e.textContent.trim())')
            R['gallery'].append({'state': state, 'page': page, 'shown': chips, 'file': shot.name, 'errors': pg.errors[:2]})
            ctx.close()
    for g in R['gallery']: print('state', g['state'], g['page'], g['shown'])


def save():
    RES.write_text(json.dumps(R, indent=1))


def section(name, fn):
    if name not in SECTIONS: return
    R['failures'] = [f for f in R['failures'] if not f.startswith(name + ':')]
    before = len(R['failures'])
    fn()
    R['failures'] = R['failures'][:before] + [f if f.startswith(name + ':') else f'{name}: {f}' for f in R['failures'][before:]]
    save()


with sync_playwright() as p:
    b = p.chromium.launch()
    PAGES = (('command', '/', '/v2/'), ('mapping', '/mapping', '/v2/mapping'),
             ('commissioning', '/commissioning', '/v2/commissioning'), ('wifi', '/wifi', '/v2/wifi'))
    section('ids', lambda: [ids_and_links(b, *x) for x in PAGES])
    def contracts():
        contract_suite(b, 'command', '/', '/v2/'); contract_suite(b, 'command_phone', '/', '/v2/', PHONE)
        contract_suite(b, 'mapping', '/mapping', '/v2/mapping'); contract_suite(b, 'wifi', '/wifi', '/v2/wifi')
        for tab in ('overview', 'steering', 'camera', 'encoders', 'imu', 'distance', 'gnss', 'other', 'system'):
            contract_suite(b, f'commissioning#{tab}', f'/commissioning#{tab}', f'/v2/commissioning#{tab}')
    section('contracts', contracts)
    section('safety', lambda: safety(b))
    section('perf', lambda: perf(b))
    section('gallery', lambda: gallery(b))
    b.close()
save()
print('FAILURES', len(R['failures'])); [print(' -', f) for f in R['failures']]
sys.exit(1 if R['failures'] else 0)
