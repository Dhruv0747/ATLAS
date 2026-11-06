#!/usr/bin/env python3
"""Track A (STAGED, inactive): publish VALIDATED Astra depth CameraInfo in lock-step with each depth frame.

The ATLAS Astra driver only publishes fallback (uncalibrated) CameraInfo. This node refuses to start unless
config/astra_calibration/depth_160x120.json passes tools/vision3d/calibration_validation.py (owner-measured physical
validation), then republishes every /astra/depth/image_raw header with the calibrated K/D on
/astra/depth/camera_info_calibrated. Read-only: no motion, servo or driver control. Runs in the Astra's private
ROS domain (77) only.
"""
import json
import sys
from pathlib import Path

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/vision3d'))
import calibration_validation as CV  # noqa: E402

CAL = ROOT / 'config/astra_calibration/depth_160x120.json'
FRAME = 'astra_depth_optical_frame'


def load_validated():
    manifest = json.loads((ROOT / 'config/vision3d_live.json').read_text())
    serial = manifest.get('device_serial') or (manifest.get('identity') or {}).get('device_serial')
    doc = json.loads(CAL.read_text())
    CV.validate_calibration(doc, serial, 160, 120, FRAME)   # raises unless physically validated
    return doc


class CalibratedInfo(Node):
    def __init__(self, doc):
        super().__init__('atlas_astra_calibrated_info')
        self.doc = doc
        self.pub = self.create_publisher(CameraInfo, '/astra/depth/camera_info_calibrated', qos_profile_sensor_data)
        self.create_subscription(Image, '/astra/depth/image_raw', self.on_depth, qos_profile_sensor_data)

    def on_depth(self, img):
        if (img.width, img.height, img.header.frame_id) != (160, 120, FRAME):
            self.get_logger().error('depth stream does not match the validated calibration; not publishing',
                                    throttle_duration_sec=5.0)
            return
        k, d = self.doc['k'], self.doc['d']
        info = CameraInfo()
        info.header = img.header
        info.width, info.height = img.width, img.height
        info.distortion_model = 'plumb_bob'
        info.d = [float(x) for x in d]
        info.k = [float(x) for x in k]
        info.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        info.p = [float(k[0]), 0.0, float(k[2]), 0.0, 0.0, float(k[4]), float(k[5]), 0.0, 0.0, 0.0, 1.0, 0.0]
        self.pub.publish(info)


def main():
    try:
        doc = load_validated()
    except Exception as e:  # never publish geometry from an unvalidated calibration
        print('atlas_astra_calibrated_info: REFUSING TO START - ' + str(e), file=sys.stderr)
        sys.exit(78)
    rclpy.init()
    node = CalibratedInfo(doc)
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
