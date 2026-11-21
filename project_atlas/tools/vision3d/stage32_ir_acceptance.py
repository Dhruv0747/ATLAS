"""Stage32 final IR acceptance: ONE IR-only Start through the real Vision Lab page, with a heartbeat pre-check.

Phase 1 (camera OFF, no Start): load the page, passively record the page's OWN /api/vision3d requests (wrapped fetch,
no extra requests) for PRECHECK_S seconds, and compare the client clock with the server's HTTP Date header. Abort without
Start if the page is hidden, its status loop gaps exceed 1.5 s, or the client loses time against the server (VM pause).
Phase 2: click Start once. Observe ONLY the page's DOM and its #diagnostics JSON (rendered by the page from its own
polls); this script sends no API requests, so it neither creates nor extends lease heartbeats. Click the IR canvas once
to read a raw value. Stop only after the runtime reports OFF (or on a failure), then press Stop.
"""
import asyncio, json, sys, time
from playwright.async_api import async_playwright

import os
BASE = os.environ.get('BASE', 'http://192.168.1.15:8088'); MODE = os.environ.get('MODE', 'ir')
WANT = {'ir': ['ir'], 'ir_depth': ['ir', 'depth'], 'rgb_ir': ['rgb', 'ir'], 'concurrent': ['depth', 'rgb'], 'depth': ['depth']}[MODE]
TAG = sys.argv[1] if len(sys.argv) > 1 else 'final'; PRECHECK_S = int(os.environ.get('PRECHECK_S', '60'))
OBSERVER = '''(() => { const hb = window.__hb = { t0: performance.now(), req: [], vis: [] }; const orig = window.fetch.bind(window);
  window.fetch = async (url, opt) => { const u = String(url), s = performance.now(); const r = await orig(url, opt);
    if (u.includes('/api/vision3d/')) { hb.req.push([Math.round(s - hb.t0), Math.round(performance.now() - s), u.split('/api/vision3d/')[1].split('?')[0],
      r.status, Date.parse(r.headers.get('date') || '') || null, Date.now()]); if (hb.req.length > 6000) hb.req.splice(0, 1000); } return r; };
  document.addEventListener('visibilitychange', () => hb.vis.push([Math.round(performance.now() - hb.t0), document.visibilityState])); })()'''
STATS = '''(from) => { const hb = window.__hb, r = hb.req.filter(x => x[2] === 'status' && x[0] >= from);
  const gaps = r.slice(1).map((x, i) => x[0] - r[i][0]); const d = r.filter(x => x[4]).map(x => x[5] - x[4]);
  return { n: r.length, gap_max_ms: gaps.length ? Math.max(...gaps) : null, gap_p50_ms: gaps.length ? gaps.slice().sort((a, b) => a - b)[gaps.length >> 1] : null,
    latency_max_ms: r.length ? Math.max(...r.map(x => x[1])) : null, drift_span_ms: d.length ? Math.max(...d) - Math.min(...d) : null,
    visibility: document.visibilityState, vis_events: hb.vis, now_ms: Math.round(performance.now() - hb.t0) }; }'''
DOM = '''() => { const q = s => document.querySelector(s); let diag = null; try { diag = JSON.parse(q('#diagnostics').textContent); } catch (e) {}
  const rt = diag && diag.runtime, sv = k => { const t = diag && diag.streams && diag.streams[k]; return t && { state: t.state, w: t.width, h: t.height, enc: t.encoding,
      fps: t.fps_observed, age: t.source_age_s, rx: t.received, rejected: t.rejected, regress: t.stamp_regressions, gap: t.max_gap_s, frame: t.frame, stamp: t.source_stamp }; };
  const ir = diag && diag.streams && diag.streams.ir;
  return { title: q('#vlTitle').textContent, ir_chip: q('#irState').textContent, ir_fps_text: q('#irFps').textContent, ir_meta: q('#irMeta').textContent,
    cpu: q('#vlCpu').textContent, ram: q('#vlRam').textContent, temp: q('#vlTemp').textContent,
    rt: rt && { state: rt.state, reason: rt.reason, mode: rt.mode, remaining_s: rt.remaining_s, cpu: rt.resources && rt.resources.cpu_percent,
      ram: rt.resources && rt.resources.ram_percent, thermal: rt.resources && rt.resources.thermal_c, astra_cpu: rt.astra_cpu_one_core_percent },
    ir: ir && { state: ir.state, w: ir.width, h: ir.height, enc: ir.encoding, fps: ir.fps_observed, age: ir.source_age_s, rx: ir.received,
      rejected: ir.rejected, regress: ir.stamp_regressions, gap: ir.max_gap_s, frame: ir.frame, stamp: ir.source_stamp },
    depth: sv('depth'), rgb: sv('rgb'), depth_chip: q('#depthState').textContent, rgb_chip: q('#rgbState').textContent, measurement: q('#measurement').textContent }; }'''
CANVAS = '''() => { const c = document.getElementById('irCanvas'); if (!c.width) return null; const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
  let mn = 255, mx = 0, s = 0; for (let i = 0; i < d.length; i += 4) { mn = Math.min(mn, d[i]); mx = Math.max(mx, d[i]); s += d[i]; }
  return { w: c.width, h: c.height, min: mn, max: mx, mean: +(s / (d.length / 4)).toFixed(1) }; }'''

async def main():
    out = {'tag': TAG, 'start_clicks': 0, 'timeline': []}
    async with async_playwright() as p:
        b = await p.chromium.launch(); ctx = await b.new_context(viewport={'width': 1440, 'height': 900})
        await ctx.add_init_script(OBSERVER); pg = await ctx.new_page(); errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        await pg.goto(BASE + '/v2/vision3d'); await pg.wait_for_timeout(PRECHECK_S * 1000)
        pre = await pg.evaluate(STATS, 0); out['precheck'] = pre
        ok = (pre['visibility'] == 'visible' and not pre['vis_events'] and pre['n'] >= PRECHECK_S and pre['gap_max_ms'] is not None
              and pre['gap_max_ms'] <= 1500 and pre['drift_span_ms'] is not None and pre['drift_span_ms'] <= 1300)
        out['precheck_pass'] = ok
        if not ok:
            out['ended_by'] = 'PRECHECK FAILED: Start not clicked'; await b.close(); json.dump(out, open(TAG + '.json', 'w'), indent=1); print(json.dumps(out, indent=1)); return
        await pg.click(f'#vlModes label[data-mode="{MODE}"]'); await pg.wait_for_timeout(500)
        if await pg.evaluate("(document.querySelector('input[name=vlMode]:checked')||{}).value") != MODE:
            out['ended_by'] = 'mode selection failed; Start not clicked'; await b.close(); json.dump(out, open(TAG + '.json', 'w'), indent=1); return
        mark = (await pg.evaluate(STATS, 0))['now_ms']; t0 = time.time()
        await pg.click('#startViewer'); out['start_clicks'] += 1
        probed = False; seen_active = False
        while time.time() - t0 < 80:
            await pg.wait_for_timeout(2000); row = await pg.evaluate(DOM); row['t'] = round(time.time() - t0, 1); out['timeline'].append(row)
            st = (row.get('rt') or {}).get('state')
            if st == 'ACTIVE': seen_active = True
            live_all = all(row.get(k) and row[k]['state'] == 'ACTIVE' for k in WANT)
            if not probed and live_all and row['t'] > 20:
                if 'depth' in WANT:   # click-to-measure on the live depth image (raw axial Z, uncalibrated)
                    db = await (await pg.query_selector('#depthImage')).bounding_box()
                    await pg.mouse.click(db['x'] + db['width'] * .5, db['y'] + db['height'] * .5); await pg.wait_for_timeout(700)
                    out['depth_measure'] = await pg.inner_text('#measurement')
                if 'ir' in WANT:
                    bb = await (await pg.query_selector('#irCanvas')).bounding_box()
                    await pg.mouse.click(bb['x'] + bb['width'] * .5, bb['y'] + bb['height'] * .5); await pg.wait_for_timeout(400)
                    out['ir_probe'] = await pg.inner_text('#irProbe'); out['ir_scale'] = await pg.inner_text('#irScale'); out['ir_canvas'] = await pg.evaluate(CANVAS)
                await pg.screenshot(path=TAG + '_live.png', full_page=True); probed = True
            if seen_active and st not in ('ACTIVE', 'CHECKING', None): out['ended_by'] = 'runtime %s: %s' % (st, row['rt'].get('reason')); break
            missing = [k for k in WANT if not (row.get(k) and row[k].get('rx'))]
            if st == 'ACTIVE' and row['t'] > 25 and missing: out['ended_by'] = 'no %s frames 25 s after Start' % '+'.join(missing); break
        else: out['ended_by'] = 'watchdog 80 s'
        out['session_heartbeat'] = await pg.evaluate(STATS, mark)
        out['final_page'] = await pg.inner_text('#vlState'); await pg.screenshot(path=TAG + '_end.png', full_page=True)
        await pg.click('#pause'); await pg.wait_for_timeout(3000); out['after_stop_page'] = await pg.inner_text('#vlState')
        out['errors'] = errs; await b.close()
    json.dump(out, open(TAG + '.json', 'w'), indent=1)
    per = {}
    for k in WANT:
        act = [r for r in out['timeline'] if r.get(k) and r[k]['state'] == 'ACTIVE']; fps = [r[k]['fps'] for r in act if r[k]['fps']]
        per[k] = {'active_polls': len(act), 'last': act[-1][k] if act else None,
                  'fps_min_med_max': [round(min(fps), 1), round(sorted(fps)[len(fps) // 2], 1), round(max(fps), 1)] if fps else None,
                  'age_max': max([r[k]['age'] for r in act if r[k]['age'] is not None] or [None]) if act else None}
    print(json.dumps({'mode': MODE, 'precheck': out['precheck'], 'ended_by': out['ended_by'], 'session_heartbeat': out['session_heartbeat'], 'ir_probe': out.get('ir_probe'),
        'ir_canvas': out.get('ir_canvas'), 'depth_measure': out.get('depth_measure'), 'streams': per,
        'guard_cpu': [r['rt']['cpu'] for r in out['timeline'] if r.get('rt') and r['rt'].get('cpu') is not None],
        'errors': out['errors']}, indent=1, default=str))

if __name__ == '__main__':
    asyncio.run(main())
