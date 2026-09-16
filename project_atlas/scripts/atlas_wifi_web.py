"""Same-origin dashboard bridge to the restricted local Wi-Fi socket."""
import ipaddress
import json
import socket
from urllib.parse import urlsplit


def same_origin(headers):
    try:
        origin = urlsplit(headers.get('Origin', ''))
        host = headers.get('Host', '')
        if origin.scheme not in ('http', 'https') or origin.netloc != host or headers.get('X-Atlas-Wifi') != '1':
            return False
        name = origin.hostname
        if name in ('jetsan-desktop.local', 'project-atlas-jetson', 'project-atlas-jetson.tail12f5ff.ts.net', 'localhost'):
            return True
        address = ipaddress.ip_address(name)
        return address.is_private or address in ipaddress.ip_network('100.64.0.0/10')
    except (ValueError, TypeError):
        return False


def request(payload):
    body = json.dumps(payload).encode()+b'\n'
    if len(body) > 4096:
        raise ValueError('Wi-Fi request too large')
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(18)
        s.connect('/run/atlas-network/wifi.sock')
        s.sendall(body)
        with s.makefile('rb') as f:
            result = f.readline(65537)
        if len(result) > 65536:
            raise ValueError('Wi-Fi response too large')
    return json.loads(result)


PAGE = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ATLAS Wi-Fi Setup</title><style>
*{box-sizing:border-box}body{margin:0;padding:20px;background:#07121e;color:#eaf7ff;font:16px system-ui,sans-serif}main{max-width:900px;margin:auto}a{color:#43d5ff}section{padding:20px;margin:18px 0;background:#162c3acc;border:1px solid #38617a;border-radius:14px}h1{font-size:26px}h2{font-size:20px}label{display:block;margin:15px 0 6px}input,select,button{font:inherit;padding:12px;border-radius:8px;border:1px solid #56829c;max-width:100%}input:not([type=checkbox]),select{width:100%;background:#061522;color:white}button{background:#0878ae;color:white;cursor:pointer;margin:8px 6px 4px 0}button:disabled{opacity:.5}#status{white-space:pre-wrap;overflow-wrap:anywhere;color:#8bdfed}.warning{color:#ffd18a}#nearby button{display:block;width:100%;text-align:left}small{color:#a3bccd}</style></head>
<body><main><a href="/">← ATLAS dashboard</a><h1>Wi-Fi Setup</h1>
<p>Save home, gate and other trusted networks. ATLAS reconnects to saved networks when available.</p>
<section><h2>Connection & dashboard address</h2><div id="status">Loading…</div><p id="links"></p>
<p class="warning">Stop the rover before changing Wi-Fi. Connecting can briefly disconnect this page. Join the new network on your phone, then reopen ATLAS using its local name or Tailscale link.</p>
<small>If connection or Internet checks fail, the previous working Wi-Fi or ATLAS-Rescue is restored. Enterprise/campus logins and router captive portals are not configured here.</small></section>
<section><h2>Saved Wi-Fi</h2><select id="saved"></select><button id="useSaved">Connect saved network</button><small>Passwords are stored securely on ATLAS, never displayed or sent to GitHub.</small></section>
<section><h2>Nearby networks</h2><button id="scan">Scan nearby Wi-Fi</button><div id="scanNote"></div><div id="nearby"></div></section>
<section><h2>Add a network</h2><form id="newWifi"><label for="ssid">Network name (SSID)</label><input id="ssid" maxlength="32" required autocomplete="off">
<label for="password">Wi-Fi password</label><input id="password" type="password" autocomplete="new-password" maxlength="64">
<label><input id="open" type="checkbox"> This is an open network (no password)</label>
<button id="connect">Save & connect</button><small>WPA/WPA2 Personal; type the SSID manually if scanning in hotspot mode cannot find it.</small></form></section>
</main><script>
const $=id=>document.getElementById(id);let lastSaved='',busy=false;
async function api(data){let r=await fetch('/api/wifi',{method:'POST',headers:{'Content-Type':'application/json','X-Atlas-Wifi':'1'},body:JSON.stringify(data),cache:'no-store'});let d=await r.json();if(!r.ok||d.error)throw Error(d.error||'Request failed');return d}
async function refresh(){try{let d=await fetch('/api/wifi',{cache:'no-store'}).then(r=>r.json());if(d.error)throw Error(d.error);$('status').textContent=(d.hotspot?'ATLAS-Rescue active':'Wi-Fi client mode')+'\n'+d.job.message+'\n'+d.dashboard_urls.join('\n');let key=JSON.stringify(d.saved);if(key!==lastSaved){let old=$('saved').value;$('saved').replaceChildren();for(let p of d.saved)$('saved').add(new Option(p.ssid+(p.preferred?' — preferred':''),p.uuid));if(d.saved.some(x=>x.uuid===old))$('saved').value=old;lastSaved=key}$('links').replaceChildren();for(let [name,url] of [['Local name',d.local_name_url],['Tailscale',d.tailscale_url]]){let a=document.createElement('a');a.href=url;a.textContent=name+': '+url;$('links').append(a,document.createElement('br'))}busy=d.job.state==='connecting';$('connect').disabled=$('useSaved').disabled=busy}catch(e){$('status').textContent='Connection unavailable. If you just switched networks, join the new Wi-Fi and reopen the local-name/Tailscale link below, or reconnect to ATLAS-Rescue if the attempt failed.'}}
async function connect(data){if(busy)return;if(!confirm('Is ATLAS stopped? This will switch its Wi-Fi connection and may disconnect this page.'))return;busy=true;$('connect').disabled=$('useSaved').disabled=true;try{let r=await api(data);$('password').value='';$('status').textContent=r.message+' Join the selected Wi-Fi on your phone to reopen the dashboard.'}catch(e){busy=false;$('status').textContent=e.message;$('connect').disabled=$('useSaved').disabled=false}}
$('scan').onclick=async()=>{$('scan').disabled=true;try{let d=await api({action:'scan'});$('scanNote').textContent=d.note||'Select a network below or enter its name manually.';$('nearby').replaceChildren();for(let n of d.networks){let b=document.createElement('button');b.textContent=n.ssid+' · '+n.signal+'% · '+n.security;b.onclick=()=>{$('ssid').value=n.ssid;$('open').checked=n.security==='OPEN';$('password').disabled=$('open').checked;$('ssid').focus()};$('nearby').append(b)}}catch(e){$('scanNote').textContent=e.message}finally{$('scan').disabled=false}};
$('useSaved').onclick=()=>{if($('saved').value)connect({action:'connect',uuid:$('saved').value})};
$('newWifi').onsubmit=e=>{e.preventDefault();connect({action:'connect',ssid:$('ssid').value,password:$('password').value,open:$('open').checked})};
$('open').onchange=()=>{$('password').disabled=$('open').checked;if($('open').checked)$('password').value=''};
refresh();setInterval(refresh,3000);
</script></body></html>'''
