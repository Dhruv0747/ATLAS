#!/usr/bin/env python3
"""AP-only captive redirect into the existing dashboard. No motion/API proxy.

Do not advertise an HTTP CAPPORT API as RFC8908 HTTPS-compliant. We use the
widely-supported HTTP connectivity-probe redirect. No HTTPS interception.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DASHBOARD = 'http://10.42.0.1:8088/'


class PortalHandler(BaseHTTPRequestHandler):
    server_version = 'ATLAS-Rescue'
    sys_version = ''

    def do_GET(self):
        body = (f'<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">'
                f'<meta http-equiv="refresh" content="0;url={DASHBOARD}"><title>ATLAS Dashboard</title></head>'
                f'<body><h1>ATLAS Rescue</h1><p>Local rover connection. Internet is unavailable.</p>'
                f'<a href="{DASHBOARD}">Open ATLAS dashboard</a></body></html>').encode()
        self.send_response(302)
        self.send_header('Location', DASHBOARD)
        self.send_header('Cache-Control', 'no-store, max-age=0')
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    do_HEAD = do_GET

    def do_POST(self):
        self.send_response(405)
        self.send_header('Allow', 'GET, HEAD')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def log_message(self, *_):
        # Avoid recording phone browsing paths, query parameters or identifiers.
        pass


def main():
    server = ThreadingHTTPServer(('10.42.0.1', 80), PortalHandler)
    server.daemon_threads = True
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
