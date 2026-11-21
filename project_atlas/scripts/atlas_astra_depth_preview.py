#!/usr/bin/env python3
"""Track A depth preview for the dashboard (read-only; ROS domain 77, started by the Track A launch).

About once a second: /astra/depth/image_raw -> colour picture (red = near, blue = far, black = no depth reading,
range 0.35-3.0 m) written atomically to web/v2/astra_depth_live.webp, plus a small status text
web/v2/astra_depth_live.txt. The dashboard's static V2 route serves both with Cache-Control: no-cache.
No control output of any kind. A crash only stops the picture; the obstacle scan is a separate process.
"""
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / 'web' / 'v2'
NEAR_M, FAR_M = 0.35, 3.0
PERIOD_S = 1.0


def colorize(depth_mm):
    """(H, W) uint16 millimetres -> (2H, 2W, 3) BGR uint8. 0 / invalid -> black; near red, far blue."""
    import cv2
    d = np.asarray(depth_mm, dtype=np.float32) * 0.001
    valid = np.isfinite(d) & (d > 0)
    norm = np.clip((d - NEAR_M) / (FAR_M - NEAR_M), 0.0, 1.0)
    img = cv2.applyColorMap(((1.0 - norm) * 255).astype(np.uint8), cv2.COLORMAP_JET)   # 255 -> red (near)
    img[~valid] = 0
    return cv2.resize(img, (d.shape[1] * 2, d.shape[0] * 2), interpolation=cv2.INTER_NEAREST)


def write_atomic(path, data):
    tmp = path.with_name('.' + path.name + '.tmp')
    tmp.write_bytes(data)
    os.replace(tmp, path)


def main():
    try:
        os.nice(10)
    except OSError:
        pass
    import cv2
    import rclpy
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import Image

    rclpy.init()
    node = rclpy.create_node('atlas_astra_depth_preview')
    state = {'last': 0.0, 'seq': 0}

    def on_depth(msg):
        now = time.monotonic()
        if now - state['last'] < PERIOD_S:
            return
        state['last'] = now
        try:
            if msg.encoding != '16UC1':
                return
            row = msg.step // 2
            arr = np.frombuffer(bytes(msg.data), dtype=np.uint16)
            if msg.is_bigendian:
                arr = arr.byteswap()
            depth = arr.reshape(msg.height, row)[:, :msg.width]
            ok, buf = cv2.imencode('.webp', colorize(depth), [cv2.IMWRITE_WEBP_QUALITY, 70])
            if not ok:
                return
            valid = depth > 0
            m = depth[valid]
            state['seq'] += 1
            write_atomic(OUT_DIR / 'astra_depth_live.webp', buf.tobytes())
            write_atomic(OUT_DIR / 'astra_depth_live.txt', json.dumps({
                'seq': state['seq'], 'unix': round(time.time(), 1), 'width': int(msg.width), 'height': int(msg.height),
                'valid_percent': round(100.0 * valid.mean(), 1),
                'nearest_m': round(float(m.min()) / 1000, 2) if m.size else None,
                'range_m': [NEAR_M, FAR_M]}).encode())
        except Exception as e:  # never crash the preview on one bad frame
            node.get_logger().warning('depth preview frame skipped: ' + str(e)[:120], throttle_duration_sec=30.0)

    node.create_subscription(Image, '/astra/depth/image_raw', on_depth, qos_profile_sensor_data)
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    sys.exit(main())
