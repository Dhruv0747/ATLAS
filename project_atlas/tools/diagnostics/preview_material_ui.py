"""PC-only static visual review: no JS, APIs, media streams or rover connection.

Run from repository checkout and open http://127.0.0.1:8767/v2/index.html.
Stop with Ctrl+C. Never run as a production web server.
"""
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path

WEB=Path(__file__).resolve().parents[2]/'web'


class Preview(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(WEB),**kwargs)
    def end_headers(self):
        self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'none'; script-src 'none'; form-action 'none'; frame-ancestors 'none'")
        self.send_header('Cache-Control','no-store')
        super().end_headers()
    def do_GET(self):
        if not self.path.startswith('/v2/'):
            self.send_error(404);return
        super().do_GET()


if __name__=='__main__':
    ThreadingHTTPServer(('127.0.0.1',8767),Preview).serve_forever()
