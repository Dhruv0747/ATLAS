"""Local synthetic UI server. Never imports rclpy, opens USB or contacts ATLAS."""
import argparse
import json
import math
from pathlib import Path
import struct
import sys
import time
from types import SimpleNamespace as N
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import atlas_vision3d_web as W
import atlas_web_v2 as V


class Sim(W.VisionService):
    def __init__(self):
        super().__init__({'topics':{k:'/sim/astra/'+k for k in W.KINDS},'modes':['SYNTHETIC fixtures — not hardware modes']})
        self.scenario='live';self.last=0
        self.pixels=struct.pack('<'+'H'*320*240,*[0 if x%23==0 else 750+x*5+y for y in range(240) for x in range(320)])
        self.rgb=bytes(v for y in range(240) for x in range(320) for v in (x%256,y%256,100))
        self.xyz=struct.pack('<'+'f'*3*2000,*[v for n in range(2000) for v in (((n%50)-25)*.02,((n//50)-20)*.02,1+math.sin(n*.1)*.1)])

    def touch(self):
        if self.scenario!='live' or time.monotonic()-self.last<.2:return
        self.last=time.monotonic();t=time.time();h=N(frame_id='sim_depth_optical_frame',stamp=N(sec=int(t),nanosec=int((t%1)*1e9)))
        def img(data,encoding,step):return N(width=320,height=240,data=data,encoding=encoding,step=step,is_bigendian=False,header=h)
        self.ingest('depth',img(self.pixels,'16UC1',640));self.ingest('rgb',img(self.rgb,'rgb8',960))
        self.ingest('ir',img(self.pixels,'mono16',640))
        self.ingest('depth_info',N(width=320,height=240,k=[280.,0,160.,0,280.,120.,0,0,1],d=[],header=h))
        fields=[N(name=k,offset=n*4,datatype=7,count=1) for n,k in enumerate('xyz')]
        self.ingest('cloud',N(width=2000,height=1,data=self.xyz,row_step=24000,point_step=12,is_bigendian=False,fields=fields,header=h))

    def status(self):
        s=super().status();s['simulated']=True;return s


def main():
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8096);a=p.parse_args();svc=Sim()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            if urlsplit(self.path).path=='/sim':
                scenario=parse_qs(urlsplit(self.path).query).get('scenario',['live'])[0]
                if scenario not in ('live','stale','unavailable'):self.send_error(400);return
                svc.scenario=scenario
                if scenario=='unavailable':svc.stop()
                data=json.dumps({'simulated':True,'scenario':scenario}).encode();self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
            if W.serve(self,svc):return
            if V.handles(self.path):V.serve(self);return
            if self.path=='/favicon.ico':self.send_response(204);self.end_headers();return
            self.send_error(404)
        def do_POST(self):self.send_error(405,'Read-only simulator')
    ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()


if __name__=='__main__':main()
