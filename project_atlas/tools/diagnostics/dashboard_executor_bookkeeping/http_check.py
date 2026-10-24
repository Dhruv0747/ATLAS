"""Dashboard HTTP/control-surface check on the imported live module: GET-only, local port, private netns.
usage (inside netns, with bench publisher running): http_check.py <tree> <out.json>"""
import json, os, sys, threading, time, urllib.request
from pathlib import Path
import rclpy.exceptions as rx
if not hasattr(rx, 'TimerCancelledError'):
    class TimerCancelledError(Exception): pass
    rx.TimerCancelledError = TimerCancelledError
tree, out = sys.argv[1], sys.argv[2]; scripts = Path(tree) / 'scripts'; sys.path.insert(0, str(scripts)); os.chdir(scripts)
import atlas_status_web as W
from http.server import ThreadingHTTPServer
srv = ThreadingHTTPServer(('127.0.0.1', 18088), W.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(8); res = {}
for path in ('/api/status', '/api/estop/state', '/v2', '/', '/api/diagnostics'):
    try:
        r = urllib.request.urlopen('http://127.0.0.1:18088' + path, timeout=10); body = r.read()
        entry = {'code': r.status, 'bytes': len(body)}
        if path.startswith('/api/'):
            d = json.loads(body); entry['keys'] = sorted(d)[:60]
            if path == '/api/status':
                ros = d.get('ros', {}); entry['ros_keys'] = len(ros)
                entry['fresh_lt_2s'] = sum(1 for v in ros.values() if isinstance(v, dict) and isinstance(v.get('age'), (int, float)) and v['age'] < 2)
                entry['web_error'] = (ros.get('web_error') or {}).get('value')
            if path == '/api/estop/state': entry['state'] = {k: d.get(k) for k in ('latched', 'reason')}
        else:
            entry['white_glass'] = b'glass' in body.lower()
        res[path] = entry
    except Exception as e:
        res[path] = {'error': repr(e)[:200]}
Path(out).write_text(json.dumps(res, indent=1)); print('HTTP CHECK DONE'); os._exit(0)
