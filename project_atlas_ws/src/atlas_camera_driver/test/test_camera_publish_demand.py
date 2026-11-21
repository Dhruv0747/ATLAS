"""Mocked tests for demand-driven camera message materialization."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock


class CompressedImage:
    """Minimal sensor_msgs/CompressedImage stand-in."""

    def __init__(self):
        self.header = SimpleNamespace(stamp=None, frame_id="")
        self.format = ""
        self.data = b""


def load_camera_module():
    """Load the driver without requiring ROS or OpenCV on the test host."""
    cv2 = types.ModuleType("cv2")
    cv2.CAP_GSTREAMER = 1
    cv2.ROTATE_180 = 2
    cv2.COLOR_BGR2LAB = 3
    cv2.COLOR_LAB2BGR = 4
    cv2.IMWRITE_JPEG_QUALITY = 5

    rclpy = types.ModuleType("rclpy")
    rclpy_node = types.ModuleType("rclpy.node")
    rclpy_node.Node = object

    sensor_msgs = types.ModuleType("sensor_msgs")
    sensor_msgs_msg = types.ModuleType("sensor_msgs.msg")
    sensor_msgs_msg.Image = type("Image", (), {})
    sensor_msgs_msg.CompressedImage = CompressedImage

    cv_bridge = types.ModuleType("cv_bridge")
    cv_bridge.CvBridge = type("CvBridge", (), {})

    stubs = {
        "cv2": cv2,
        "rclpy": rclpy,
        "rclpy.node": rclpy_node,
        "sensor_msgs": sensor_msgs,
        "sensor_msgs.msg": sensor_msgs_msg,
        "cv_bridge": cv_bridge,
    }
    previous = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        path = (
            Path(__file__).resolve().parents[1]
            / "atlas_camera_driver"
            / "camera_node.py"
        )
        spec = importlib.util.spec_from_file_location("camera_node_under_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, old_module in previous.items():
            if old_module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old_module


CAMERA_MODULE = load_camera_module()


class Publisher:
    """Publisher double with an explicit matched-subscriber count."""

    def __init__(self, subscriber_count):
        self.subscriber_count = subscriber_count
        self.published = []

    def get_subscription_count(self):
        return self.subscriber_count

    def publish(self, message):
        self.published.append(message)


class CameraPublishDemandTests(unittest.TestCase):
    """Exercise each raw/compressed subscriber combination."""

    def make_node(self, raw_subscribers, compressed_subscribers):
        node = CAMERA_MODULE.CameraNode.__new__(CAMERA_MODULE.CameraNode)
        node.cap = SimpleNamespace(read=MagicMock(return_value=(True, "captured")))
        node.rotate_180 = True
        node.adaptive_contrast = False
        node.pub_raw = Publisher(raw_subscribers)
        node.pub_compressed = Publisher(compressed_subscribers)
        node.bridge = SimpleNamespace(
            cv2_to_imgmsg=MagicMock(
                return_value=SimpleNamespace(
                    header=SimpleNamespace(stamp=None, frame_id="")
                )
            )
        )
        node.frame_id = "camera_link"
        node.jpeg_quality = 75
        node.get_clock = MagicMock(
            return_value=SimpleNamespace(
                now=MagicMock(
                    return_value=SimpleNamespace(
                        to_msg=MagicMock(return_value="stamp")
                    )
                )
            )
        )
        node.get_logger = MagicMock()

        CAMERA_MODULE.cv2.rotate = MagicMock(return_value="rotated")
        CAMERA_MODULE.cv2.imencode = MagicMock(
            return_value=(
                True,
                SimpleNamespace(tobytes=MagicMock(return_value=b"jpeg")),
            )
        )
        return node

    def test_no_subscribers_still_drains_and_rotates_capture(self):
        node = self.make_node(0, 0)

        node._tick()

        node.cap.read.assert_called_once_with()
        CAMERA_MODULE.cv2.rotate.assert_called_once_with(
            "captured", CAMERA_MODULE.cv2.ROTATE_180
        )
        node.bridge.cv2_to_imgmsg.assert_not_called()
        CAMERA_MODULE.cv2.imencode.assert_not_called()
        self.assertEqual(node.pub_raw.published, [])
        self.assertEqual(node.pub_compressed.published, [])

    def test_raw_subscriber_gets_unchanged_bgr_message(self):
        node = self.make_node(1, 0)

        node._tick()

        node.bridge.cv2_to_imgmsg.assert_called_once_with(
            "rotated", encoding="bgr8"
        )
        CAMERA_MODULE.cv2.imencode.assert_not_called()
        self.assertEqual(len(node.pub_raw.published), 1)
        message = node.pub_raw.published[0]
        self.assertEqual(message.header.stamp, "stamp")
        self.assertEqual(message.header.frame_id, "camera_link")
        self.assertEqual(node.pub_compressed.published, [])

    def test_compressed_subscriber_gets_same_quality_and_payload(self):
        node = self.make_node(0, 1)

        node._tick()

        node.bridge.cv2_to_imgmsg.assert_not_called()
        CAMERA_MODULE.cv2.imencode.assert_called_once_with(
            ".jpg",
            "rotated",
            [CAMERA_MODULE.cv2.IMWRITE_JPEG_QUALITY, 75],
        )
        self.assertEqual(node.pub_raw.published, [])
        self.assertEqual(len(node.pub_compressed.published), 1)
        message = node.pub_compressed.published[0]
        self.assertEqual(message.header.stamp, "stamp")
        self.assertEqual(message.header.frame_id, "camera_link")
        self.assertEqual(message.format, "jpeg")
        self.assertEqual(message.data, b"jpeg")

    def test_both_subscribers_share_the_same_frame_stamp(self):
        node = self.make_node(1, 1)

        node._tick()

        self.assertEqual(len(node.pub_raw.published), 1)
        self.assertEqual(len(node.pub_compressed.published), 1)
        self.assertIs(
            node.pub_raw.published[0].header.stamp,
            node.pub_compressed.published[0].header.stamp,
        )


if __name__ == "__main__":
    unittest.main()
