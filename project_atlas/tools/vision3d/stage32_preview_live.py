"""Stage32 owner-approved live test: ONE Depth-only session with the UNCALIBRATED 3D preview (21 Oct 2026, 19:16 approval).

Same safety model as stage32_ir_acceptance.py: one headless page is the viewer; 60-s heartbeat pre-check (no Start if it
fails); exactly one Start; this script sends NO API requests itself (it only observes the page's own fetches and reads
the DOM / #diagnostics), so it neither creates nor extends lease heartbeats. Interactions are pure UI (checkbox, drag,
wheel, shift-drag, click on the 3D canvas). "Pause preview" is used briefly so view-change checks compare one held cloud;
the camera keeps streaming and the page keeps polling status while paused. No repeat Start on any failure.
"""
import asyncio, hashlib, json, os, sys, time
from pathlib import Path
from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage32_ir_acceptance as ACC   # noqa: E402  (OBSERVER, STATS, DOM)

BASE = os.environ.get('BASE', 'http://192.168.1.15:8088'); TAG = sys.argv[1] if len(sys.argv) > 1 else 'preview_live'
PRECHECK_S = int(os.environ.get('PRECHECK_S', '60'))
TAP = ("(()=>{const f=CanvasRenderingContext2D.prototype.fillText;window.__texts=new Set();"
       "CanvasRenderingContext2D.prototype.fillText=function(t,...a){if(this.canvas&&this.canvas.id==='cloudCanvas')window.__texts.add(String(t));return f.call(this,t,...a)}})()")
RAWSTATS = '''(from) => { const r = window.__hb.req.filter(x => x[2] === 'raw' && x[0] >= from && x[3] === 200);
  const cl = window.__hb.req.filter(x => x[2] === 'cloud' && x[0] >= from).length;
  const span = r.length > 1 ? (r[r.length - 1][0] - r[0][0]) / 1000 : null;
  return { raw_ok: r.length, preview_updates_per_s: span ? +((r.length - 1) / span).toFixed(2) : null, raw_latency_max_ms: r.length ? Math.max(...r.map(x => x[1])) : null, cloud_requests: cl }; }'''
HASH = "document.getElementById('cloudCanvas').toDataURL()"
FIND_PT = '''(() => { const c = document.getElementById('cloudCanvas'), x = c.getContext('2d').getImageData(0, 0, c.width, c.height);
  const r = c.getBoundingClientRect(), sx = r.width / c.width;
  for (let d = 0; d < 260; d += 2) for (let a = 0; a < 6.28; a += .25) { const px = Math.round(c.width / 2 + d * Math.cos(a)), py = Math.round(c.height / 2 + d * Math.sin(a));
    if (px < 1 || py < 60 || px >= c.width || py >= c.height) continue; const i = (py * c.width + px) * 4;
    if (x.data[i + 3] > 0 && (x.data[i] + x.data[i + 1] + x.data[i + 2]) > 200) return [r.left + px * sx, r.top + py * sx]; } return null; })()'''


def h(s):
    return hashlib.md5(s.encode()).hexdigest()


async def main():
    out = {'tag': TAG, 'start_clicks': 0, 'timeline': [], 'preview': {}}
    async with async_playwright() as p:
        b = await p.chromium.launch(); ctx = await b.new_context(viewport={'width': 1440, 'height': 900})
        await ctx.add_init_script(ACC.OBSERVER); await ctx.add_init_script(TAP); pg = await ctx.new_page(); errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        await pg.goto(BASE + '/v2/vision3d'); await pg.wait_for_timeout(PRECHECK_S * 1000)
        out['mode_notes'] = await pg.evaluate("Object.fromEntries([...document.querySelectorAll('#vlModes label')].map(l=>[l.dataset.mode,(l.querySelector('[data-note]')||{}).textContent]))")
        out['preview_disabled_before_start'] = await pg.is_disabled('#showPreview')
        pre = await pg.evaluate(ACC.STATS, 0); out['precheck'] = pre
        ok = (pre['visibility'] == 'visible' and not pre['vis_events'] and pre['n'] >= PRECHECK_S and pre['gap_max_ms'] is not None
              and pre['gap_max_ms'] <= 1500 and pre['drift_span_ms'] is not None and pre['drift_span_ms'] <= 1300)
        out['precheck_pass'] = ok
        if not ok:
            out['ended_by'] = 'PRECHECK FAILED: Start not clicked'; await b.close(); Path(TAG + '.json').write_text(json.dumps(out, indent=1)); print(json.dumps(out, indent=1)); return
        await pg.click('#vlModes label[data-mode="depth"]'); await pg.wait_for_timeout(500)
        if await pg.evaluate("(document.querySelector('input[name=vlMode]:checked')||{}).value") != 'depth':
            out['ended_by'] = 'mode selection failed; Start not clicked'; await b.close(); Path(TAG + '.json').write_text(json.dumps(out, indent=1)); return
        mark = (await pg.evaluate(ACC.STATS, 0))['now_ms']; t0 = time.time()
        await pg.click('#startViewer'); out['start_clicks'] += 1
        seen_active = False; ticked_at = None; tested = False
        while time.time() - t0 < 80:
            await pg.wait_for_timeout(1000)
            row = await pg.evaluate(ACC.DOM); row['t'] = round(time.time() - t0, 1)
            row['cloud_chip'] = await pg.inner_text('#cloudState'); row['cloud_meta'] = await pg.inner_text('#cloudMeta')
            out['timeline'].append(row); st = (row.get('rt') or {}).get('state')
            seen_active = seen_active or st == 'ACTIVE'
            depth_live = row.get('depth') and row['depth']['state'] == 'ACTIVE'
            if depth_live and ticked_at is None and not await pg.is_disabled('#showPreview'):
                await pg.check('#showPreview'); ticked_at = row['t']; out['preview']['ticked_at_s'] = ticked_at
                out['preview']['raw_mark'] = (await pg.evaluate(ACC.STATS, 0))['now_ms']
            if ticked_at is not None and not tested and row['t'] >= ticked_at + 6 and depth_live:
                P = out['preview']
                P['warn_visible'] = await pg.is_visible('#previewWarn'); P['chip'] = row['cloud_chip']; P['meta'] = row['cloud_meta']
                P['canvas_texts'] = sorted(await pg.evaluate('[...window.__texts]'))
                cv = await pg.query_selector('#cloudCanvas'); await cv.scroll_into_view_if_needed(); await pg.wait_for_timeout(300)
                await cv.screenshot(path=TAG + '_cloud_live.png')
                await pg.click('#freeze'); await pg.wait_for_timeout(1300)          # hold one real cloud for the view checks
                await cv.scroll_into_view_if_needed(); await pg.wait_for_timeout(300); bb = await cv.bounding_box(); cx, cy = bb['x'] + bb['width'] / 2, bb['y'] + bb['height'] / 2
                h0 = h(await pg.evaluate(HASH)); h0b = h(await pg.evaluate(HASH))
                await pg.mouse.move(cx, cy); await pg.mouse.down(); await pg.mouse.move(cx + 140, cy + 50, steps=8); await pg.mouse.up(); await pg.wait_for_timeout(250)
                h1 = h(await pg.evaluate(HASH)); await cv.screenshot(path=TAG + '_cloud_orbit.png')
                await pg.mouse.wheel(0, -300); await pg.wait_for_timeout(250); h2 = h(await pg.evaluate(HASH))
                await pg.keyboard.down('Shift'); await pg.mouse.move(cx, cy); await pg.mouse.down(); await pg.mouse.move(cx - 90, cy, steps=6); await pg.mouse.up(); await pg.keyboard.up('Shift'); await pg.wait_for_timeout(250)
                h3 = h(await pg.evaluate(HASH))
                P['view_changes'] = {'held_cloud_stable': h0 == h0b, 'orbit': h1 != h0, 'zoom': h2 != h1, 'pan': h3 != h2}
                pt = await pg.evaluate(FIND_PT)
                if pt:
                    await pg.mouse.click(pt[0], pt[1]); await pg.wait_for_timeout(300)
                P['point_click'] = await pg.inner_text('#measurement')
                await cv.screenshot(path=TAG + '_cloud_interacted.png')
                await pg.click('#resetView'); await pg.click('#freeze'); tested = True
            if seen_active and st not in ('ACTIVE', 'CHECKING', None):
                out['ended_by'] = 'runtime %s: %s' % (st, row['rt'].get('reason')); break
            if st == 'ACTIVE' and row['t'] > 25 and not (row.get('depth') and row['depth'].get('rx')):
                out['ended_by'] = 'no depth frames 25 s after Start'; break
        else:
            out['ended_by'] = 'watchdog 80 s'
        out['session_heartbeat'] = await pg.evaluate(ACC.STATS, mark)
        if 'raw_mark' in out['preview']:
            out['preview']['fetch'] = await pg.evaluate(RAWSTATS, out['preview']['raw_mark'])
        out['after_end'] = {'preview_disabled': await pg.is_disabled('#showPreview'), 'preview_checked': await pg.is_checked('#showPreview')}
        out['final_page'] = await pg.inner_text('#vlState'); await pg.screenshot(path=TAG + '_end.png', full_page=True)
        await pg.click('#pause'); await pg.wait_for_timeout(3000); out['after_stop_page'] = await pg.inner_text('#vlState')
        out['errors'] = errs; await b.close()
    Path(TAG + '.json').write_text(json.dumps(out, indent=1, default=str))
    act = [r for r in out['timeline'] if r.get('depth') and r['depth']['state'] == 'ACTIVE']
    pts = [int(r['cloud_meta'].split(' points')[0]) for r in out['timeline'] if r['cloud_meta'].split(' ')[0].isdigit()]
    fps = [r['depth']['fps'] for r in act if r['depth']['fps']]
    print(json.dumps({'precheck': out['precheck'], 'mode_notes': out['mode_notes'], 'ended_by': out['ended_by'], 'heartbeat': out['session_heartbeat'],
                      'preview': out['preview'], 'points_min_max': [min(pts), max(pts)] if pts else None,
                      'depth_fps_min_med_max': [min(fps), sorted(fps)[len(fps) // 2], max(fps)] if fps else None,
                      'depth_age_max_s': max([r['depth']['age'] for r in act if r['depth']['age'] is not None] or [None]) if act else None,
                      'depth_last': act[-1]['depth'] if act else None,
                      'guard_cpu': [r['rt']['cpu'] for r in out['timeline'] if r.get('rt') and r['rt'].get('cpu') is not None],
                      'ram': [r['rt']['ram'] for r in out['timeline'] if r.get('rt') and r['rt'].get('ram') is not None],
                      'thermal': [r['rt']['thermal'] for r in out['timeline'] if r.get('rt') and r['rt'].get('thermal')][-1:],
                      'after_end': out['after_end'], 'errors': out['errors']}, indent=1, default=str))


if __name__ == '__main__':
    asyncio.run(main())
