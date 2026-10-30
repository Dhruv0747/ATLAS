"""Isolated optional YOLO worker; input is existing viewer RGB, no subscriptions."""
import base64
import ctypes
import hashlib
import json
import os
import resource
import select
import signal
import sys
import time
from pathlib import Path


def main():
    parent=os.getppid()
    ctypes.CDLL(None).prctl(1,signal.SIGKILL)  # Linux parent-death cleanup
    if os.getppid()!=parent:raise RuntimeError('parent changed')
    signal.alarm(5)  # independent startup deadline, including native engine load
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    feature,model,expected=sys.argv[1:]
    if feature not in ('object','target','body'):raise ValueError('unsupported feature')
    if hashlib.sha256(Path(model).read_bytes()).hexdigest()!=expected:raise ValueError('model hash mismatch')
    from trt_yolo_detector import TensorRTYOLO
    from atlas_vision_features import detections,Tracker
    import numpy as np
    detector=TensorRTYOLO(model);tracker=Tracker();deadline=time.monotonic()+60
    try:
        while time.monotonic()<deadline:
            if not select.select([sys.stdin],[],[],2)[0]:break
            signal.alarm(2)  # bounded IPC/inference even if parent guard stalls
            line=sys.stdin.buffer.readline(9_000_000)
            if not line:break
            if not line.endswith(b'\n'):raise ValueError('oversized frame')
            m=json.loads(line);w,h=m['width'],m['height']
            if type(w)!=int or type(h)!=int or not 0<w<=1920 or not 0<h<=1080:raise ValueError('dimensions')
            if not 0<=time.time_ns()-m['stamp_ns']<=500_000_000:raise ValueError('stale input')
            raw=base64.b64decode(m['rgb'],validate=True)
            if len(raw)!=w*h*3:raise ValueError('payload size')
            started=time.process_time();wall=time.monotonic()
            rows=detections(detector.infer(np.frombuffer(raw,np.uint8).reshape(h,w,3)),w,h,feature=='body')
            if feature!='object':rows=tracker.update(rows,m['stamp_ns'])
            result=dict(stamp_ns=m['stamp_ns'],stamp_ns_exact=str(m['stamp_ns']),width=w,height=h,detections=rows,
                        inference_s=time.monotonic()-wall,cpu_s=time.process_time()-started,
                        peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            print(json.dumps(result,allow_nan=False),flush=True)
    finally:detector.close()


if __name__=='__main__':
    try:main()
    except Exception as e:
        print(json.dumps({'error':str(e)[:500]}),flush=True)
        sys.exit(1)
