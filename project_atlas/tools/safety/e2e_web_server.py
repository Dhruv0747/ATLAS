#!/usr/bin/env python3
"""Run the real rover-status-web module (ROS layer + HTTP handler) for isolated E-STOP tests.

Only on a private DDS domain (ROS_DOMAIN_ID != 0, ROS_LOCALHOST_ONLY=1) and on 127.0.0.1:<port>,
never on 8088. SIGUSR1 sets SHUTDOWN_PENDING in-process (the shutdown ACTION is never called: it
would power the Jetson off); SIGUSR2 clears it.  Usage: e2e_web_server.py <scripts_dir> <port>
"""
import importlib, os, signal, sys, threading
assert os.environ.get('ROS_DOMAIN_ID') not in (None, '', '0'), 'isolated ROS domain required'
assert os.environ.get('ROS_LOCALHOST_ONLY') == '1', 'ROS_LOCALHOST_ONLY=1 required'
assert int(sys.argv[2]) != 8088
sys.path.insert(0, sys.argv[1])
web = importlib.import_module('atlas_status_web')
from http.server import ThreadingHTTPServer
server = ThreadingHTTPServer(('127.0.0.1', int(sys.argv[2])), web.Handler)
server.daemon_threads = True
signal.signal(signal.SIGUSR1, lambda *_: web.SHUTDOWN_PENDING.set())
signal.signal(signal.SIGUSR2, lambda *_: web.SHUTDOWN_PENDING.clear())
signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
print('e2e web server ready', flush=True)
try:
    server.serve_forever(poll_interval=0.1)
finally:
    server.server_close(); web.ROS.close()
