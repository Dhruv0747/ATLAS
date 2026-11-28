"""Synthetic Depth session against the NEW receiver (raw depth route) + new UI: UNCALIBRATED preview. No ROS/USB/ATLAS."""
import asyncio, hashlib, json, struct, sys, threading, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from types import SimpleNamespace as N
R = Path(__file__).parent; sys.path.insert(0, str(R / 'scripts'))
import atlas_vision3d_web as W, atlas_web_v2 as V
from playwright.async_api import async_playwright
man = json.loads((R / 'config/vision3d_live.json').read_text()); man.pop('viewer_runtime', None)
svc = W.VisionService(man); T0 = [None]
def z(u, v):
    if u < 4: return 0                                  # shadow band (no reading)
    if 60 <= u < 100 and 40 <= v < 80: return 1200     # box 1.2 m
    return 2500 + 4 * v                                  # wall tilting away toward the bottom
DEPTH = b''.join(struct.pack('<H', z(u, v)) for v in range(120) for u in range(160))
def runtime():
    lim = {'cpu_percent': 75, 'ram_percent': 80, 'temperature_c': 70}
    if T0[0] is None: return {'state': 'OFF', 'reason': '', 'mode': None, 'limits': lim}
    t = time.time() - T0[0]; base = {'mode': 'depth', 'worker_pid': 900, 'driver_pid': 901, 'limits': lim, 'remaining_s': max(0, 40 - t)}
    if t < 2: return dict(base, state='CHECKING')
    if t < 40: return dict(base, state='ACTIVE')
    return dict(base, state='OFF', reason='60-second session complete; explicit Start required', driver_stopped=True)
def feeder():
    while True:
        time.sleep(0.1)
        if T0[0] is None: continue
        t = time.time() - T0[0]
        if 3 < t < 40:
            now = time.time(); h = N(frame_id='astra_depth_optical_frame', stamp=N(sec=int(now), nanosec=int((now % 1) * 1e9)))
            svc.ingest('depth', N(width=160, height=120, data=DEPTH, encoding='16UC1', step=320, is_bigendian=False, header=h))
        if t > 40 and svc.messages: svc.stop()
threading.Thread(target=feeder, daemon=True).start()
orig = svc.status; svc.status = lambda: dict(orig(), runtime=runtime())
REQ = []
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        REQ.append(self.path)
        if W.serve(self, svc): return
        if V.handles(self.path): V.serve(self); return
        self.send_error(404)
    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0); b = json.loads(self.rfile.read(n) or b'{}')
        if b.get('action') == 'start': T0[0] = time.time()
        d = json.dumps({'state': 'CHECKING'}).encode(); self.send_response(202); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(d))); self.end_headers(); self.wfile.write(d)
srv = ThreadingHTTPServer(('127.0.0.1', 8112), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
TAP = "(()=>{const f=CanvasRenderingContext2D.prototype.fillText;window.__texts=new Set();CanvasRenderingContext2D.prototype.fillText=function(t,...a){if(this.canvas.id==='cloudCanvas')window.__texts.add(String(t));return f.call(this,t,...a)}})()"
async def main():
    out = {}
    async with async_playwright() as p:
        b = await p.chromium.launch(); ctx = await b.new_context(viewport={'width': 1440, 'height': 900}); await ctx.add_init_script(TAP)
        pg = await ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        await pg.goto('http://127.0.0.1:8112/v2/vision3d'); await pg.wait_for_timeout(2000)
        out['preview_disabled_when_off'] = await pg.is_disabled('#showPreview')
        await pg.click('#vlModes label[data-mode="depth"]'); await pg.click('#startViewer'); await pg.wait_for_timeout(7000)
        out['enabled_when_depth_live'] = not await pg.is_disabled('#showPreview')
        out['checked_by_default'] = await pg.is_checked('#showPreview')
        await pg.check('#showPreview'); await pg.wait_for_timeout(3000)
        out['warn_visible'] = await pg.is_visible('#previewWarn'); out['chip'] = await pg.inner_text('#cloudState'); out['meta'] = await pg.inner_text('#cloudMeta')
        out['canvas_texts'] = sorted(await pg.evaluate('[...window.__texts]'))
        await pg.click('#freeze'); await pg.wait_for_timeout(1500)   # hold one picture so changes are caused by the view only
        cv = await pg.query_selector('#cloudCanvas'); await cv.scroll_into_view_if_needed(); await pg.wait_for_timeout(300); bb = await cv.bounding_box(); cx, cy = bb['x'] + bb['width'] / 2, bb['y'] + bb['height'] / 2
        hsh = lambda: pg.evaluate("document.getElementById('cloudCanvas').toDataURL()")
        h0 = hashlib.md5((await hsh()).encode()).hexdigest()
        await cv.screenshot(path=str(R / 'pv_front.png'))
        await pg.mouse.move(cx, cy); await pg.mouse.down(); await pg.mouse.move(cx + 120, cy + 40, steps=8); await pg.mouse.up(); await pg.wait_for_timeout(300)
        h1 = hashlib.md5((await hsh()).encode()).hexdigest(); await cv.screenshot(path=str(R / 'pv_orbit.png'))
        await pg.mouse.wheel(0, -400); await pg.wait_for_timeout(300); h2 = hashlib.md5((await hsh()).encode()).hexdigest()
        await pg.keyboard.down('Shift'); await pg.mouse.move(cx, cy); await pg.mouse.down(); await pg.mouse.move(cx - 80, cy, steps=6); await pg.mouse.up(); await pg.keyboard.up('Shift'); await pg.wait_for_timeout(300)
        h3 = hashlib.md5((await hsh()).encode()).hexdigest()
        out['view_changes'] = {'orbit': h1 != h0, 'zoom': h2 != h1, 'pan': h3 != h2}
        # click the densest projected point near the centre
        pt = await pg.evaluate("(()=>{const c=document.getElementById('cloudCanvas'),x=c.getContext('2d').getImageData(0,0,c.width,c.height);const r=c.getBoundingClientRect(),sx=r.width/c.width;for(let d=0;d<200;d+=2)for(let a=0;a<6.28;a+=.3){const px=Math.round(c.width/2+d*Math.cos(a)),py=Math.round(c.height/2+d*Math.sin(a)),i=(py*c.width+px)*4;if(px>0&&py>0&&px<c.width&&py<c.height&&x.data[i+3]>0&&(x.data[i]+x.data[i+1]+x.data[i+2])>200&&!(x.data[i]>200&&x.data[i+1]>120&&x.data[i+2]<80))return [r.left+px*sx,r.top+py*sx]}return null})()")
        if pt: await pg.mouse.click(pt[0], pt[1]); await pg.wait_for_timeout(300)
        out['click'] = await pg.inner_text('#measurement')
        await pg.screenshot(path=str(R / 'pv_full.png'), full_page=True)
        await pg.click('#freeze'); await pg.wait_for_timeout(36000)
        out['after_end'] = {'title': await pg.inner_text('#vlTitle'), 'preview_disabled': await pg.is_disabled('#showPreview'), 'checked': await pg.is_checked('#showPreview')}
        out['errors'] = errs; await b.close()
    out['raw_requests'] = sum('raw?kind=depth' in r for r in REQ); out['cloud_requests'] = sum('/api/vision3d/cloud' in r for r in REQ)
    print(json.dumps(out, indent=1))
asyncio.run(main())
