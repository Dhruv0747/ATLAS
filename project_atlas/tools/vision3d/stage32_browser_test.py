"""Stage32 SYNTHETIC browser check of the Vision Lab IR viewer and cloud gating. Local only: no ROS, USB or ATLAS contact.
Synthetic fixtures prove page logic only; they say nothing about the real Astra IR sensor."""
import asyncio, json, struct, sys, threading, time
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace as N
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT / 'scripts'))
import sim_server as S
import atlas_vision3d_web as W
from playwright.async_api import async_playwright

MANIFEST = json.loads((ROOT / 'config/vision3d_live.json').read_text())
IR8 = bytes((x * 255 // 319) if y < 120 else (40 + (x + y) % 9) for y in range(240) for x in range(320))   # gradient top, dim noise bottom


class Sim32(S.Sim):
    def __init__(self):
        super().__init__(); self.manifest['mode_support'] = MANIFEST['mode_support']
    n = 0
    def status(self):
        s = super().status()
        s['runtime'] = {'state': 'ACTIVE', 'mode': 'ir', 'remaining_s': 40, 'worker_pid': 1, 'driver_pid': 2, 'simulated': True,
                        'limits': {'cpu_percent': 75, 'ram_percent': 80, 'temperature_c': 70}, 'resources': {'cpu_percent': 50, 'ram_percent': 40}}
        return s
    def ingest(self, kind, m):
        if kind == 'ir' and m.encoding != 'mono8': return      # replace the generic mono16 fixture with the driver's MONO8 format
        return super().ingest(kind, m)
    def touch(self):
        due = self.scenario == 'live' and time.monotonic() - self.last >= .2
        super().touch()
        if due:
            t = time.time(); h = N(frame_id='sim_ir_optical_frame', stamp=N(sec=int(t), nanosec=int((t % 1) * 1e9)))
            Sim32.n += 1; frame = bytes([Sim32.n % 200]) + IR8[1:]           # top-left pixel changes every frame
            self.ingest('ir', N(width=320, height=240, data=frame, encoding='mono8', step=320, is_bigendian=False, header=h))


def serve(port):
    svc = Sim32()
    class H(S.BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            if W.serve(self, svc): return
            if S.V.handles(self.path): S.V.serve(self); return
            self.send_error(404)
        def do_POST(self): self.send_error(405, 'Read-only simulator')
    srv = ThreadingHTTPServer(('127.0.0.1', port), H); threading.Thread(target=srv.serve_forever, daemon=True).start(); return srv


async def main(out_dir):
    srv = serve(8097); res = {}
    async with async_playwright() as p:
        b = await p.chromium.launch(); errs = []
        for name, vp in (('desktop', {'width': 1440, 'height': 900}), ('mobile', {'width': 390, 'height': 844})):
            pg = await (await b.new_context(viewport=vp)).new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
            await pg.goto('http://127.0.0.1:8097/v2/vision3d'); await pg.wait_for_timeout(3500)
            r = await pg.evaluate('''()=>{const q=s=>document.querySelector(s);const modes={};
              for(const l of document.querySelectorAll('#vlModes label')){const i=l.querySelector('input');modes[i.value]={disabled:i.disabled,note:l.querySelector('[data-note]').textContent}}
              const c=q('#irCanvas');const px=c.width?Array.from(c.getContext('2d').getImageData(0,0,c.width,c.height).data.filter((_,i)=>i%4==0)):[];
              return {modes,ir_state:q('#irState').textContent,ir_w:c.width,ir_h:c.height,ir_min:px.length?Math.min(...px.slice(0,320*120)):null,ir_max:px.length?Math.max(...px.slice(0,320*120)):null,
                ir_scale:q('#irScale').textContent,cloud_cal:q('#cloudCal').textContent,cloud_chip:q('#cloudState').textContent,show_cloud_disabled:q('#showCloud').disabled,
                hscroll:document.documentElement.scrollWidth>document.documentElement.clientWidth}}''')
            await pg.locator('#irCanvas').scroll_into_view_if_needed(); bb = await (await pg.query_selector('#irCanvas')).bounding_box()
            r['hit'] = await pg.evaluate(f"document.elementFromPoint({bb['x']+bb['width']*0.5},{bb['y']+bb['height']*0.1})?.id")
            await pg.mouse.click(bb['x'] + bb['width'] * 0.99, bb['y'] + bb['height'] * 0.1); await pg.wait_for_timeout(300)
            r['probe_right_top'] = await pg.inner_text('#irProbe')
            await pg.mouse.click(bb['x'] + 2, bb['y'] + bb['height'] * 0.1); await pg.wait_for_timeout(300)
            r['probe_left_top'] = await pg.inner_text('#irProbe')
            r['freeze_disabled_without_session'] = await pg.evaluate("document.getElementById('freeze').disabled")
            px0 = "document.getElementById('irCanvas').getContext('2d').getImageData(0,0,1,1).data[0]"
            a1 = await pg.evaluate(px0); await pg.wait_for_timeout(1200); r['live_frames_change'] = a1 != await pg.evaluate(px0)
            await pg.click('#freeze'); await pg.wait_for_timeout(300); f1 = await pg.evaluate(px0)
            await pg.wait_for_timeout(1500); r['frozen_frame_kept'] = f1 == await pg.evaluate(px0); r['freeze_label'] = await pg.inner_text('#freeze')
            r['run_text_frozen'] = await pg.inner_text('#runtimeState')
            await pg.click('#freeze'); await pg.wait_for_timeout(1200); r['resumed_changes'] = f1 != await pg.evaluate(px0)
            await pg.screenshot(path=str(Path(out_dir) / f's32_sim_{name}.png'), full_page=True)
            res[name] = r
        res['ir_display_cost_ms_this_pc'] = await pg.evaluate('''()=>{const n=320*240,v=new Uint8Array(n);for(let i=0;i<n;i++)v[i]=(i*37)&255;
          const c=document.createElement('canvas');c.width=320;c.height=240;const g=c.getContext('2d');const t=performance.now();
          for(let r=0;r<20;r++){const s=v.slice().sort(),lo=s[n*0.02|0],hi=Math.max(lo+1,s[n*0.98|0]);const im=g.createImageData(320,240);
          for(let i=0;i<n;i++){const x=Math.max(0,Math.min(255,Math.round((v[i]-lo)*255/(hi-lo))));im.data[i*4]=im.data[i*4+1]=im.data[i*4+2]=x;im.data[i*4+3]=255}g.putImageData(im,0,0)}
          return +((performance.now()-t)/20).toFixed(2)}''')
        res['page_errors'] = errs; await b.close()
    srv.shutdown(); print(json.dumps(res, indent=1))
    d = res['desktop']; m = d['modes']
    checks = {'depth_cloud disabled': m['depth_cloud']['disabled'], 'ir selectable (untested)': not m['ir']['disabled'],
              'ir drawn native size': (d['ir_w'], d['ir_h']) == (320, 240), 'stretch spans 0..255': (d['ir_min'], d['ir_max']) == (0, 255),
              'probe raw 252 at u=316': 'intensity 252 (of 255) at pixel 316' in d['probe_right_top'], 'probe raw 0 left': 'intensity 0 ' in d['probe_left_top'],
              'cloud gated': d['show_cloud_disabled'] and d['cloud_chip'] == 'Blocked' and 'not validated' in d['cloud_cal'].lower(),
              'pause preview holds frame': d['freeze_label'] == 'Resume preview' and d['frozen_frame_kept'] and d['live_frames_change'] and d['resumed_changes'], 'no page errors': not res['page_errors'], 'mobile no h-scroll': not res['mobile']['hscroll']}
    print(json.dumps(checks, indent=1)); return all(checks.values())

if __name__ == '__main__':
    raise SystemExit(0 if asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else '.')) else 1)
