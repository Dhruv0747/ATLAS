"""20-second read-only JPEG source attribution; no driver/settings changes."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.request
import cv2
import numpy as np
import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():p.error('new output directory required')
    a.out.mkdir();rclpy.init();node=rclpy.create_node('atlas_camera_readonly_probe')
    hashes={};counts={};first={};http=[]
    def receive(msg,kind):
        raw=bytes(msg.data);h=hashlib.sha256(raw).hexdigest();hashes[h]=kind;counts[kind]=counts.get(kind,0)+1
        if kind not in first:
            frame=cv2.imdecode(np.frombuffer(raw,dtype=np.uint8),cv2.IMREAD_COLOR)
            first[kind]=dict(width=int(frame.shape[1]),height=int(frame.shape[0]),bytes=len(raw))
            (a.out/(kind+'.jpg')).write_bytes(raw)
    for kind,topic in [('source','/camera/image_raw/compressed'),('ai','/camera/detections/compressed')]:
        node.create_subscription(CompressedImage,topic,lambda m,k=kind:receive(m,k),qos_profile_sensor_data)
    start=time.monotonic();next_http=start
    try:
        while time.monotonic()-start<20:
            rclpy.spin_once(node,timeout_sec=.02)
            if time.monotonic()>=next_http:
                try:
                    with urllib.request.urlopen('http://127.0.0.1:8088/camera.jpg',timeout=1) as r:raw=r.read()
                    http.append(hashlib.sha256(raw).hexdigest())
                except Exception:pass
                next_http=time.monotonic()+.25
    finally:node.destroy_node();rclpy.shutdown()
    result=dict(counts=counts,first_frame=first,http_samples=len(http),exact_matches={kind:sum(hashes.get(h)==kind for h in http) for kind in ('source','ai')},unmatched=sum(h not in hashes for h in http))
    (a.out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
if __name__=='__main__':main()
