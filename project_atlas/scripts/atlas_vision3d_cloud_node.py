#!/usr/bin/env python3
"""Stage32 XYZ PointCloud2 for the Vision Lab: PRIVATE ROS domain 77 only, launched only by the viewer worker.

Subscribes /astra/depth/image_raw and publishes /astra/points (sensor_msgs/PointCloud2, x/y/z float32 metres, depth
optical frame, the depth image's own timestamp). Refuses to run unless:
  * ROS_DOMAIN_ID is the Vision Lab private domain (never the production graph), and
  * config/astra_calibration/depth_160x120.json passes the validated-calibration gate (no factory NaN, no FOV guess).
Bounded: at most 5 clouds/s and 6,000 points each. No other publishers, services, recording or file output.
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import atlas_vision3d_geometry as G   # noqa: E402

PRIVATE_DOMAIN = '77'
PUBLISH_HZ = 5.0
DEPTH_TOPIC = '/astra/depth/image_raw'
CLOUD_TOPIC = '/astra/points'


def admission(env=os.environ, manifest_path=ROOT / 'config/vision3d_live.json', calibration_path=None):
    """Return the validated calibration document or raise with the refusal reason."""
    if env.get('ROS_DOMAIN_ID') != PRIVATE_DOMAIN:
        raise RuntimeError('refusing: not in the private Vision Lab ROS domain')
    manifest = json.loads(Path(manifest_path).read_text())
    st = G.calibration_state(manifest, calibration_path)
    if st['state'] != 'VALIDATED':
        raise RuntimeError('CALIBRATION BLOCKED: ' + st['reason'])
    return st['calibration']


class Rate:
    def __init__(self, hz, clock=time.monotonic):
        self.dt, self.clock, self.last = 1.0 / hz, clock, -1e9

    def ready(self):
        now = self.clock()
        if now - self.last < self.dt:
            return False
        self.last = now
        return True


def to_msg(points, header, PointCloud2, PointField):
    f = G.pointcloud2_fields(points)
    msg = PointCloud2()
    msg.header = header                      # same stamp and optical frame as the source depth image
    msg.height, msg.width = f['height'], f['width']
    msg.fields = [PointField(name=n, offset=o, datatype=PointField.FLOAT32, count=1) for n, o in f['fields']]
    msg.is_bigendian, msg.point_step, msg.row_step, msg.is_dense = False, f['point_step'], f['row_step'], f['is_dense']
    msg.data = f['data']
    return msg


def main():                                   # pragma: no cover - needs ROS and a validated calibration
    try:
        calibration = admission()
    except Exception as e:
        print(str(e), flush=True)
        return 3
    import rclpy
    from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
    from sensor_msgs.msg import Image, PointCloud2, PointField
    rclpy.init()
    node = rclpy.create_node('atlas_vision3d_cloud')
    qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT, durability=DurabilityPolicy.VOLATILE)
    pub = node.create_publisher(PointCloud2, CLOUD_TOPIC, qos)
    rate = Rate(PUBLISH_HZ)

    def on_depth(msg):
        if not rate.ready():
            return
        try:
            points, _ = G.backproject(msg, calibration)
        except ValueError as e:
            node.get_logger().warning('cloud skipped: %s' % e)
            return
        pub.publish(to_msg(points, msg.header, PointCloud2, PointField))
    node.create_subscription(Image, DEPTH_TOPIC, on_depth, qos)
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
