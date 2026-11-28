# Stage32: ONE bounded Vision Lab session in the given mode through the real page. Clicks Start exactly once, never again.
# Polls only through the page (no SSH while streaming). Stops on guard stop / session end / no frames, then presses Stop.
import asyncio, json, sys, time
from playwright.async_api import async_playwright
import os; BASE = os.environ.get('BASE', 'http://192.168.1.15:8088'); MODE = sys.argv[1]; TAG = sys.argv[2]
WANT = {'ir': ['ir'], 'ir_depth': ['ir', 'depth'], 'concurrent': ['depth', 'rgb'], 'rgb_ir': ['rgb', 'ir']}[MODE]
STATUS_JS = '''async()=>{const r=await fetch('/api/vision3d/status',{cache:'no-store'});const s=await r.json();const o={rt:s.runtime?{state:s.runtime.state,reason:s.runtime.reason,mode:s.runtime.mode,remaining_s:s.runtime.remaining_s,
  resources:s.runtime.resources,failed:s.runtime.failed_resources,astra_cpu:s.runtime.astra_cpu_one_core_percent,astra_rss_kib:s.runtime.astra_rss_kib,win:s.runtime.cpu_window_s,elapsed:s.runtime.elapsed_s}:null,streams:{}};
  for(const k of ['depth','rgb','ir','cloud']){const t=s.streams[k];o.streams[k]={state:t.state,w:t.width,h:t.height,enc:t.encoding,fps:t.fps_observed,age:t.source_age_s,rx:t.received,gap:t.max_gap_s,frame:t.frame,regress:t.stamp_regressions,rejected:t.rejected,throttled:t.viewer_throttled,reason:t.reason}}
  return o}'''
async def main():
    out = {'mode': MODE, 'timeline': [], 'start_clicks': 0}
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await (await b.new_context(viewport={'width': 1440, 'height': 900})).new_page(); errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        await pg.goto(BASE + '/v2/vision3d'); await pg.wait_for_timeout(4000)
        await pg.click(f'#vlModes label[data-mode="{MODE}"]'); await pg.wait_for_timeout(300)
        out['mode_selected'] = await pg.evaluate("(document.querySelector('input[name=vlMode]:checked')||{}).value")
        if out['mode_selected'] != MODE: raise SystemExit('mode selection failed; Start NOT clicked')
        out['before'] = await pg.evaluate(STATUS_JS)
        t0 = time.time(); await pg.click('#startViewer'); out['start_clicks'] += 1
        shots = {12: '12s', 30: '30s', 50: '50s'}; probed = False; first_frames = None
        while time.time() - t0 < 75:
            await pg.wait_for_timeout(2000); t = round(time.time() - t0, 1)
            try: row = await pg.evaluate(STATUS_JS)
            except Exception as e: row = {'error': str(e)}
            row['t'] = t; row['title'] = await pg.inner_text('#vlTitle'); out['timeline'].append(row)
            st = (row.get('rt') or {}).get('state')
            live = all(row.get('streams', {}).get(k, {}).get('state') == 'ACTIVE' for k in WANT)
            if live and first_frames is None: first_frames = t; out['first_all_streams_s'] = t
            for s, n in list(shots.items()):
                if t >= s: await pg.screenshot(path=f'{TAG}_{n}.png', full_page=True); shots.pop(s)
            if 'ir' in WANT and not probed and row.get('streams', {}).get('ir', {}).get('state') == 'ACTIVE' and t > 15:
                bb = await (await pg.query_selector('#irCanvas')).bounding_box()
                await pg.mouse.click(bb['x'] + bb['width'] * .5, bb['y'] + bb['height'] * .5); await pg.wait_for_timeout(400)
                out['ir_probe'] = await pg.inner_text('#irProbe'); out['ir_scale'] = await pg.inner_text('#irScale'); probed = True
                out['ir_canvas'] = await pg.evaluate('''()=>{const c=document.getElementById('irCanvas');const d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let mn=255,mx=0,s=0,n=0;
                  for(let i=0;i<d.length;i+=4){mn=Math.min(mn,d[i]);mx=Math.max(mx,d[i]);s+=d[i];n++}return {w:c.width,h:c.height,min:mn,max:mx,mean:+(s/n).toFixed(1)}}''')
            if st in ('RESOURCE BLOCKED',) or (st not in ('ACTIVE', 'CHECKING', None) and t > 6): out['ended_by'] = f'runtime {st}: {(row.get("rt") or {}).get("reason")}'; break
            if st == 'ACTIVE' and first_frames is None and t > 25: out['ended_by'] = 'no frames on all requested streams 25 s after start'; break
        else: out['ended_by'] = 'watchdog 75 s'
        await pg.screenshot(path=f'{TAG}_end.png', full_page=True)
        out['final_page'] = await pg.inner_text('#vlState')
        await pg.click('#pause'); await pg.wait_for_timeout(3500)
        out['after_stop'] = await pg.evaluate(STATUS_JS); out['after_stop_page'] = await pg.inner_text('#vlState')
        out['errors'] = errs; await b.close()
    json.dump(out, open(f'{TAG}.json', 'w'), indent=1)
    tl = [r for r in out['timeline'] if 'streams' in r]
    def col(k, f): return [r['streams'][k][f] for r in tl if r['streams'][k]['state'] == 'ACTIVE']
    summ = {'mode': MODE, 'ended_by': out.get('ended_by'), 'first_all_streams_s': out.get('first_all_streams_s'), 'ir_probe': out.get('ir_probe'), 'ir_canvas': out.get('ir_canvas'),
            'errors': errs, 'astra_cpu_core': [r['rt'].get('astra_cpu') for r in tl if r.get('rt') and r['rt'].get('astra_cpu') is not None], 'astra_rss_kib_max': max([r['rt'].get('astra_rss_kib') or 0 for r in tl if r.get('rt')] or [0]),
            'ram_max': max([((r['rt'].get('resources') or {}).get('ram_percent') or 0) for r in tl if r.get('rt')] or [0]),
            'thermal_max': max([max(((r['rt'].get('resources') or {}).get('thermal_c') or {0: 0}).values()) for r in tl if r.get('rt')] or [0]),
            'samples_cpu': [round(r['rt']['resources']['cpu_percent'], 1) for r in tl if r.get('rt') and isinstance((r['rt'].get('resources') or {}).get('cpu_percent'), (int, float))]}
    for k in ('depth', 'rgb', 'ir'):
        rx = col(k, 'rx')
        if rx: summ[k] = {'res': f"{col(k,'w')[-1]}x{col(k,'h')[-1]}", 'enc': col(k, 'enc')[-1], 'frame': col(k, 'frame')[-1], 'rx_last': rx[-1], 'fps_min_med_max': (lambda f: [round(min(f),1), round(sorted(f)[len(f)//2],1), round(max(f),1)] if f else None)([x for x in col(k, 'fps') if x is not None]), 'age_max': max(a for a in col(k, 'age') if a is not None), 'gap_max': col(k, 'gap')[-1], 'regress': col(k, 'regress')[-1], 'rejected': col(k, 'rejected')[-1], 'throttled': col(k, 'throttled')[-1]}
    print(json.dumps(summ, indent=1))
asyncio.run(main())
