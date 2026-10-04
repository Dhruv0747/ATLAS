import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FILTER_PATH = ROOT / "scripts" / "atlas_scan_self_filter.py"
SERVICE_PATH = ROOT / "systemd" / "user" / "atlas-scan-filter.service"


class Stamp:
    def __init__(self, sec=0, nanosec=0):
        self.sec = sec
        self.nanosec = nanosec


class Header:
    def __init__(self):
        self.stamp = Stamp()
        self.frame_id = ""


class LaserScan:
    def __init__(self):
        self.header = Header()
        self.angle_min = 0.0
        self.angle_max = 0.0
        self.angle_increment = 0.0
        self.time_increment = 0.0
        self.scan_time = 0.0
        self.range_min = 0.0
        self.range_max = 0.0
        self.ranges = []
        self.intensities = []


class Int32:
    def __init__(self, data=0):
        self.data = data


class Recorder:
    def __init__(self):
        self.messages = []

    def publish(self, message):
        self.messages.append(message)


def load_filter_module():
    modules = {
        "rclpy": types.ModuleType("rclpy"),
        "rclpy.executors": types.ModuleType("rclpy.executors"),
        "rclpy.node": types.ModuleType("rclpy.node"),
        "rclpy.qos": types.ModuleType("rclpy.qos"),
        "sensor_msgs": types.ModuleType("sensor_msgs"),
        "sensor_msgs.msg": types.ModuleType("sensor_msgs.msg"),
        "std_msgs": types.ModuleType("std_msgs"),
        "std_msgs.msg": types.ModuleType("std_msgs.msg"),
    }

    class ExternalShutdownException(Exception):
        pass

    class Node:
        pass

    class Policy:
        RELIABLE = "reliable"
        VOLATILE = "volatile"
        KEEP_LAST = "keep_last"

    class QoSProfile:
        def __init__(self, **values):
            self.values = values

    modules["rclpy.executors"].ExternalShutdownException = ExternalShutdownException
    modules["rclpy.node"].Node = Node
    modules["rclpy.qos"].DurabilityPolicy = Policy
    modules["rclpy.qos"].HistoryPolicy = Policy
    modules["rclpy.qos"].QoSProfile = QoSProfile
    modules["rclpy.qos"].ReliabilityPolicy = Policy
    modules["rclpy.qos"].qos_profile_sensor_data = object()
    modules["sensor_msgs.msg"].LaserScan = LaserScan
    modules["std_msgs.msg"].Int32 = Int32

    previous = {name: sys.modules.get(name) for name in modules}
    sys.modules.update(modules)
    try:
        spec = importlib.util.spec_from_file_location(
            "atlas_scan_self_filter_under_test", FILTER_PATH
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, old_module in previous.items():
            if old_module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old_module


class AtlasScanSelfFilterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_filter_module()

    def make_filter(self):
        node = self.module.AtlasScanSelfFilter.__new__(
            self.module.AtlasScanSelfFilter
        )
        node.publisher = Recorder()
        node.filtered_pub = Recorder()

        def publication_clock_must_not_be_used():
            raise AssertionError("filter must not replace acquisition time")

        node.get_clock = publication_clock_must_not_be_used
        return node

    def test_preserves_driver_acquisition_timestamp_and_scan_timing(self):
        node = self.make_filter()
        source = LaserScan()
        source.header.frame_id = "laser_frame"
        source.header.stamp = Stamp(sec=123, nanosec=456_789)
        source.angle_min = 0.0
        source.angle_max = 1.0
        source.angle_increment = 1.0
        source.time_increment = 0.00037
        source.scan_time = 0.132
        source.range_min = 0.15
        source.range_max = 8.0
        source.ranges = [0.2, 1.0]
        source.intensities = [10.0, 20.0]

        node._scan(source)

        target = node.publisher.messages[-1]
        self.assertEqual(
            (target.header.stamp.sec, target.header.stamp.nanosec),
            (123, 456_789),
        )
        self.assertEqual(
            (source.header.stamp.sec, source.header.stamp.nanosec),
            (123, 456_789),
        )
        self.assertEqual(target.header.frame_id, "laser_frame")
        self.assertEqual(target.time_increment, source.time_increment)
        self.assertEqual(target.scan_time, source.scan_time)

    def test_filtering_does_not_mutate_raw_ranges(self):
        node = self.make_filter()
        source = LaserScan()
        source.header.stamp = Stamp(sec=1, nanosec=2)
        source.angle_min = 0.0
        source.angle_increment = 1.0
        source.range_min = 0.15
        source.range_max = 8.0
        source.ranges = [0.2, 1.0]
        source.intensities = [10.0, 20.0]

        node._scan(source)

        target = node.publisher.messages[-1]
        self.assertEqual(source.ranges, [0.2, 1.0])
        self.assertEqual(target.ranges[1], 1.0)
        self.assertEqual(node.filtered_pub.messages[-1].data, 1)

    def test_service_keeps_single_filter_boundary(self):
        source = FILTER_PATH.read_text(encoding="utf-8")
        service = SERVICE_PATH.read_text(encoding="utf-8")
        self.assertIn("LaserScan, '/scan_raw'", source)
        self.assertIn("LaserScan, '/scan'", source)
        self.assertIn("depth=1", source)
        self.assertIn("atlas_scan_self_filter.py", service)


if __name__ == "__main__":
    unittest.main()
