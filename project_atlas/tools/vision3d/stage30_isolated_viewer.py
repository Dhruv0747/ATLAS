"""Temporary loopback-only existing Vision Lab host, maximum240 seconds.

No production install, service operation, motor interface or frame recording.
Camera lifetime/guards are still the existing bounded runtime's responsibility.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import signal
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[2]
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
os.environ['ATLAS_WEB_V2_DIR']=str(ROOT/'web/v2')
os.environ['ATLAS_VISION3D_MANIFEST']=str(ROOT/'config/vision3d_live.json')
os.environ['ATLAS_VISION3D_STATE_PATH']=str(ROOT/'stage30-viewer-state.json')
sys.path.insert(0,str(ROOT/'scripts'))
import atlas_vision3d_web as W
import atlas_web_v2 as V
from atlas_vision3d_runtime import SESSION


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if W.serve(self):return
        if V.handles(self.path):V.serve(self);return
        self.send_error(404)
    def do_POST(self):
        if W.serve(self,post=True):return
        self.send_error(404)
    def log_message(self,*args):pass


def main():
    # Production web already has these native ROS types loaded. Warm the isolated
    # equivalent before readiness (caller may pace this new process). No ROS init.
    cpu=time.process_time();wall=time.monotonic()
    from rclpy.serialization import deserialize_message
    from rclpy.type_support import check_for_type_support
    from rosidl_runtime_py.utilities import get_message
    for typ in ('sensor_msgs/msg/Image','sensor_msgs/msg/CameraInfo'):
        check_for_type_support(get_message(typ))
    print('STAGE30_TYPES_WARM '+str(time.process_time()-cpu)+' '+str(time.monotonic()-wall),flush=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.daemon_threads=True
    def stop(*_):threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    timer=threading.Timer(240,stop);timer.daemon=True;timer.start()
    print('STAGE30_LISTEN '+str(server.server_port),flush=True)
    try:server.serve_forever(poll_interval=.25)
    finally:timer.cancel();SESSION.stop();W.SERVICE.stop();server.server_close()


if __name__=='__main__':main()
