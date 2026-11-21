"""Explicit offline localhost UI fixture, never used by production."""
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
import json,math,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import atlas_map3d_web as api

def main():
    with tempfile.TemporaryDirectory() as d:
        api.ROOT=Path(d)  # payload default root passed explicitly below
        session=Path(d)/'20261030T120000-12345678';session.mkdir()
        (session/'status.json').write_text(json.dumps({'state':'SYNTHETIC UI TEST'}))
        (session/'cloud.json').write_text(json.dumps(dict(label='SYNTHETIC UI TEST — NOT AN ATLAS MAP',frame='map_3d',points=[[x/10,y/10,math.sin(x/5)*.2] for x in range(-20,21) for y in range(-20,21)])))
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                try:
                    if self.path.startswith('/api/map3d/'):
                        body=json.dumps(api.payload(self.path,Path(d))).encode();mime='application/json'
                    else:
                        name={'/v2/map3d':'map3d.html','/v2/map3d.js':'map3d.js','/v2/glass.css':'glass.css'}.get(self.path)
                        if name is None:raise ValueError('unknown route')
                        body=(ROOT/'web/v2'/name).read_bytes();mime='text/html' if name.endswith('html') else 'text/javascript' if name.endswith('js') else 'text/css'
                    self.send_response(200);self.send_header('Content-Type',mime);self.end_headers();self.wfile.write(body)
                except Exception:self.send_error(404)
            def log_message(self,*a):pass
        HTTPServer(('127.0.0.1',8769),Handler).serve_forever()

if __name__=='__main__':main()
