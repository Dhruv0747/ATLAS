"""Local offline UI fixture. Never connects to Jetson or starts a camera."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import json,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import atlas_vision_feature_lab as lab
import atlas_vision3d_web as web
import atlas_web_v2 as static


def main():
    with tempfile.TemporaryDirectory() as d:
        lab.LAB=lab.Lab(d)
        viewer=web.VisionService(manifest={'topics':{},'modes':[]})
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith(('/api/vision3d/features','/api/vision3d/feature-report')):
                    web.serve(self);return
                if self.path=='/api/vision3d/status':
                    value=viewer.status();value['runtime']=dict(state='OFF',reason='OFFLINE UI FIXTURE')
                    raw=json.dumps(value).encode()
                    self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(raw);return
                if static.serve(self):return
                self.send_error(404)
            def do_POST(self):
                if self.path=='/api/vision3d/features':web.serve(self,post=True)
                else:self.send_error(403,'Offline fixture: camera controls forbidden')
            def log_message(self,*args):pass
        ThreadingHTTPServer(('127.0.0.1',8770),Handler).serve_forever()


if __name__=='__main__':main()
