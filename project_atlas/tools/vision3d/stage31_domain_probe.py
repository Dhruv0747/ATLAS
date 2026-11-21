#!/usr/bin/env python3
"""Stage31 camera-free mechanism check, PRIVATE ROS domain only. Opens no camera, touches no production topic/domain.
A synthetic 160x120 16UC1 publisher and the real Vision Lab RosTransport (domain 77) run in this one process for N s."""
import sys, time, threading, json
sys.path.insert(0, '/tmp/s31')
import atlas_vision3d_web as W
import atlas_vision3d_runtime as R
import rclpy
from rclpy.context import Context
from rclpy.executors import SingleThreadedExecutor
from sensor_msgs.msg import Image, CameraInfo
N = float(sys.argv[1]) if len(sys.argv) > 1 else 12
assert R.ISOLATED_DOMAIN_ID == 77
t0 = time.monotonic()
pc = Context(); rclpy.init(context=pc, domain_id=R.ISOLATED_DOMAIN_ID)
pn = rclpy.create_node('s31_synthetic_depth', context=pc)
pi = pn.create_publisher(Image, '/astra/depth/image_raw', 1); pinfo = pn.create_publisher(CameraInfo, '/astra/depth/camera_info', 1)
img = Image(); img.height, img.width, img.encoding, img.step = 120, 160, '16UC1', 320; img.data = bytes(320 * 120)
sent = [0]
def tick():
    img.header.stamp = pn.get_clock().now().to_msg(); pi.publish(img); sent[0] += 1
    if sent[0] % 30 == 1:
        ci = CameraInfo(); ci.header.stamp = img.header.stamp; ci.width, ci.height = 160, 120; pinfo.publish(ci)
pn.create_timer(1 / 30.0, tick)
pe = SingleThreadedExecutor(context=pc); pe.add_node(pn)
threading.Thread(target=pe.spin, daemon=True).start()
got = {}; first = {}
def cb(kind, msg):
    got[kind] = got.get(kind, 0) + 1; first.setdefault(kind, round(time.monotonic() - t0, 3))
tr = W.viewer_transport(); tr.start({'depth': '/astra/depth/image_raw', 'depth_info': '/astra/depth/camera_info'}, cb)
time.sleep(N)
tr.stop(); pe.shutdown(timeout_sec=2); pn.destroy_node(); pc.shutdown()
el = time.monotonic() - t0
print(json.dumps({'domain': R.ISOLATED_DOMAIN_ID, 'elapsed_s': round(el, 2), 'published': sent[0], 'received': got,
                  'first_frame_s': first, 'receive_hz_depth': round(got.get('depth', 0) / max(el - first.get('depth', el), 1e-6), 2)}))
