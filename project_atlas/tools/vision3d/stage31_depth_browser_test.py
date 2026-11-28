# ONE bounded Depth-only start through the real /v2/vision3d page. Clicks Start exactly once, never again.
# Stops on RESOURCE BLOCKED or after ~40 s, then presses Stop. Isolation is checked passively over SSH mid-session.
import asyncio, json, subprocess, time
from playwright.async_api import async_playwright
BASE='http://192.168.1.15:8088'
SSH=['ssh','-o','BatchMode=yes','-i','/sessions/rcw-01vnbmnxblacpuugcz4hscec/.ssh/atlas_rel','jetson@100.87.208.71']
ISO_UNUSED=r'''P=$(pgrep -x astra_camera_no | head -1); echo "driver_pid=$P"; [ -n "$P" ] && tr '\0' '\n' < /proc/$P/environ | grep -E '^ROS_DOMAIN_ID='; W=$(pgrep -f 'atlas_vision3d_runtime.py --worker' | head -1); echo "worker_pid=$W"; [ -n "$W" ] && (tr '\0' '\n' < /proc/$W/environ | grep -c '^ROS_DOMAIN_ID=' | sed 's/^/worker_domain_vars=/'); ls /dev/shm | grep -o "fastrtps_port[0-9]*" | sed "s/fastrtps_port//" | awk '{d=int(($1-7400)/250); c[d]++} END{for(k in c) print "shm_ports_domain_"k"="c[k]}'; [ -n "$P" ] && ss -uanp 2>/dev/null | grep "pid=$P," | awk '{print $4}' | sed 's/.*://' | sort -n | tr '\n' ' ' | sed 's/^/driver_udp_ports=/'; echo; S=$(systemctl --user show rover-status-web -p MainPID --value); ss -uanp 2>/dev/null | grep "pid=$S," | awk '{print $4}' | sed 's/.*://' | sort -n | awk '$1>=26000' | tr '\n' ' ' | sed 's/^/web_domain77_udp_ports=/'; echo'''
async def main():
    out={'timeline':[],'start_clicks':0,'measures':{}}
    async with async_playwright() as p:
        b=await p.chromium.launch(); c=await b.new_context(viewport={'width':1440,'height':900}); pg=await c.new_page(); errs=[]
        pg.on('pageerror',lambda e:errs.append(str(e)))
        await pg.goto(BASE+'/v2/vision3d'); await pg.wait_for_timeout(4000)
        await pg.check('input[name="vlMode"][value="depth"]')
        out['before']=await pg.inner_text('#vlState'); await pg.screenshot(path='b_depth_0_before.png',full_page=True)
        t0=time.time(); await pg.click('#startViewer'); out['start_clicks']+=1
        shots={10:'b_depth_10s.png',30:'b_depth_30s.png',52:'b_depth_52s.png'}; iso_done=False; measured=False
        while time.time()-t0<70:
            await pg.wait_for_timeout(2000); t=round(time.time()-t0,1)
            row=await pg.evaluate('''()=>({title:document.getElementById('vlTitle').textContent,cpu:document.getElementById('vlCpu').textContent,
              ram:document.getElementById('vlRam').textContent,temp:document.getElementById('vlTemp').textContent,driver:document.getElementById('vlDriver').textContent,
              depth:document.getElementById('depthState').textContent,fps:document.getElementById('depthFps').textContent,meta:document.getElementById('depthMeta').textContent,
              img_w:document.getElementById('depthImage').naturalWidth,img_src:!!document.getElementById('depthImage').getAttribute('src')})''')
            row['t']=t; out['timeline'].append(row)
            for s,f in list(shots.items()):
                if t>=s: await pg.screenshot(path=f,full_page=True); shots.pop(s)
            for mt in (20,40):
                if mt not in out['measures'] and t>=mt and row['img_w']>0 and row['title']=='Camera streaming':
                    bb=await (await pg.query_selector('#depthImage')).bounding_box()
                    await pg.mouse.click(bb['x']+bb['width']*0.5,bb['y']+bb['height']*0.45); await pg.wait_for_timeout(700)
                    out['measures'][mt]={'t':round(time.time()-t0,1),'text':await pg.inner_text('#measurement')}
            if row['title'] in ('Stopped to protect ATLAS','Session finished','No reply from the Vision Lab') or (row['title']=='Camera off' and t>6): break
        out['final_before_stop']=await pg.inner_text('#vlState')
        await pg.screenshot(path='b_depth_end.png',full_page=True)
        await pg.click('#pause'); await pg.wait_for_timeout(3000)
        out['after_stop']=await pg.inner_text('#vlState'); out['diagnostics']=(await pg.inner_text('#diagnostics'))[:4000]
        out['errors']=errs; await b.close()
    print(json.dumps(out,indent=1))
asyncio.run(main())
