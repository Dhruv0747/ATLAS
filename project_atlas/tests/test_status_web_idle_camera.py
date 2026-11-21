#!/usr/bin/env python3
"""Regression tests for demand-driven status-web camera caching."""

import ast
from pathlib import Path
import threading
import time
import unittest


SOURCE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "atlas_status_web.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def class_node(name):
    return next(
        node for node in TREE.body
        if isinstance(node, ast.ClassDef) and node.name == name
    )


def method_node(class_name, method_name):
    owner = class_node(class_name)
    return next(
        node for node in owner.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )


def load_class(name, namespace):
    module = ast.Module(body=[class_node(name)], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(SOURCE_PATH), "exec"), namespace)
    return namespace[name]


def load_method(method_name, namespace, dependencies=()):
    methods = [
        method_node("AtlasRosNode", name)
        for name in (*dependencies, method_name)
    ]
    owner = ast.ClassDef(
        name="Subject",
        bases=[],
        keywords=[],
        body=methods,
        decorator_list=[],
    )
    module = ast.Module(body=[owner], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(SOURCE_PATH), "exec"), namespace)
    return namespace["Subject"]


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class FakeDemand:
    def __init__(self, active):
        self.is_active = active
        self.touches = 0

    def active(self, _now=None):
        return self.is_active

    def touch(self):
        self.touches += 1


class LengthOnlyData:
    def __len__(self):
        return 4321

    def __bytes__(self):
        raise AssertionError("idle ingress must not copy the JPEG payload")


class Message:
    def __init__(self, data):
        self.data = data


class FakeNode:
    def __init__(self, publishers=1):
        self.publishers = publishers
        self.created = []
        self.destroyed = []

    def create_subscription(self, message_type, topic, callback, qos):
        subscription = (message_type, topic, callback, qos)
        self.created.append(subscription)
        return subscription

    def destroy_subscription(self, subscription):
        self.destroyed.append(subscription)
        return True

    def count_publishers(self, topic):
        self.publisher_topic = topic
        return self.publishers


class StatusWebIdleCameraTests(unittest.TestCase):
    def test_client_demand_expires_and_renews(self):
        clock = FakeClock()
        demand_type = load_class(
            "CameraClientDemand",
            {"threading": threading, "time": time},
        )
        demand = demand_type(2.0, clock=clock)

        self.assertFalse(demand.active())
        demand.touch()
        self.assertTrue(demand.active())
        clock.now = 2.0
        self.assertTrue(demand.active())
        clock.now = 2.001
        self.assertFalse(demand.active())
        demand.touch()
        self.assertTrue(demand.active())

    def test_idle_compressed_ingress_updates_health_without_copying(self):
        subject_type = load_method(
            "_camera_cb",
            {
                "time": time,
                "CAMERA_HEALTH_PERIOD_SECONDS": 1.0,
            },
        )
        subject = subject_type()
        subject.last_compressed_camera = 0.0
        subject.last_camera_health = 0.0
        subject.camera_clients = FakeDemand(False)
        subject.prev_motion_gray = object()
        updates = {}
        subject._set = lambda key, value: updates.__setitem__(key, value)

        subject._camera_cb(Message(LengthOnlyData()))

        self.assertEqual(updates["camera_info"]["bytes"], 4321)
        self.assertFalse(updates["camera_info"]["streaming"])
        self.assertIn("no camera client", updates["camera_info"]["motion"])
        self.assertIsNone(subject.prev_motion_gray)

    def test_active_compressed_ingress_keeps_latest_frame(self):
        subject_type = load_method(
            "_camera_cb",
            {
                "time": time,
                "CAMERA_HEALTH_PERIOD_SECONDS": 1.0,
            },
        )
        subject = subject_type()
        subject.last_compressed_camera = 0.0
        subject.last_camera_health = 0.0
        subject.last_motion_check = time.time()
        subject.camera_clients = FakeDemand(True)
        subject.ai_mode = "eco"
        subject.yolo_ready = False
        subject.data = {}
        subject.lock = threading.Lock()
        subject.camera_frame_condition = threading.Condition(subject.lock)

        subject._camera_cb(Message(bytearray(b"jpeg")))

        self.assertEqual(subject.data["camera_frame"]["value"], b"jpeg")
        self.assertTrue(subject.data["camera_info"]["value"]["streaming"])

    def test_annotated_frame_copy_requires_object_mode_and_client(self):
        subject_type = load_method("_ai_camera_cb", {})
        subject = subject_type()
        subject.ai_mode = "object"
        subject.camera_clients = FakeDemand(False)
        subject._set = lambda *_args: self.fail("idle annotated frame was copied")
        subject._ai_camera_cb(Message(LengthOnlyData()))

        subject.ai_mode = "eco"
        subject.camera_clients = FakeDemand(True)
        subject._ai_camera_cb(Message(LengthOnlyData()))

        updates = {}
        subject.ai_mode = "object"
        subject.camera_clients = FakeDemand(True)
        subject.lock = threading.Lock()
        subject.camera_frame_condition = threading.Condition(subject.lock)
        subject._set = lambda key, value: updates.__setitem__(key, value)
        subject._ai_camera_cb(Message(bytearray(b"annotated")))
        self.assertEqual(updates["ai_camera_frame"], b"annotated")

    def test_camera_get_renews_demand_and_rejects_stale_frame(self):
        subject_type = load_method(
            "camera_frame",
            {
                "time": time,
                "CAMERA_FRAME_MAX_AGE_SECONDS": 2.0,
                "CAMERA_WAKE_TIMEOUT_SECONDS": 0.01,
            },
            dependencies=("_fresh_camera_source",),
        )
        subject = subject_type()
        subject.camera_clients = FakeDemand(False)
        subject.ai_mode = "eco"
        subject.lock = threading.Lock()
        subject.camera_frame_condition = threading.Condition(subject.lock)
        subject.data = {
            "camera_frame": {"value": b"old", "ts": time.time() - 3.0},
        }

        self.assertIsNone(subject.camera_frame())
        self.assertEqual(subject.camera_clients.touches, 1)
        subject.data["camera_frame"] = {"value": b"new", "ts": time.time()}
        self.assertEqual(subject.camera_frame(), b"new")

    def test_first_request_waits_for_post_idle_frame(self):
        subject_type = load_method(
            "camera_frame",
            {
                "time": time,
                "CAMERA_FRAME_MAX_AGE_SECONDS": 2.0,
                "CAMERA_WAKE_TIMEOUT_SECONDS": 0.25,
            },
            dependencies=("_fresh_camera_source",),
        )
        subject = subject_type()
        subject.camera_clients = FakeDemand(False)
        subject.ai_mode = "eco"
        subject.lock = threading.Lock()
        subject.camera_frame_condition = threading.Condition(subject.lock)
        subject.data = {}
        result = []

        worker = threading.Thread(target=lambda: result.append(subject.camera_frame()))
        worker.start()
        time.sleep(0.02)
        with subject.camera_frame_condition:
            subject.data["camera_frame"] = {"value": b"fresh", "ts": time.time()}
            subject.camera_frame_condition.notify_all()
        worker.join(timeout=1.0)

        self.assertFalse(worker.is_alive())
        self.assertEqual(result, [b"fresh"])

    def test_all_camera_endpoints_renew_the_same_lease(self):
        for method_name in (
            "camera_frame",
            "camera_panel_frame",
            "camera_overview_frame",
        ):
            rendered = ast.unparse(method_node("AtlasRosNode", method_name))
            self.assertIn("self.camera_clients.touch()", rendered)

    def test_subscription_exists_only_during_camera_demand(self):
        subject_type = load_method(
            "_camera_subscription_tick",
            {
                "time": time,
                "CompressedImage": object(),
                "qos_profile_sensor_data": object(),
                "CAMERA_HEALTH_PERIOD_SECONDS": 1.0,
            },
        )
        subject = subject_type()
        subject.node = FakeNode()
        subject.camera_clients = FakeDemand(True)
        subject.ai_mode = "eco"
        subject.camera_subscription = None
        subject.ai_camera_subscription = None
        subject.last_camera_health = 0.0
        subject.last_camera_bytes = 4321
        subject.prev_motion_gray = object()
        subject.lock = threading.Lock()
        subject.camera_frame_condition = threading.Condition(subject.lock)
        subject.data = {}
        subject.panel_camera_frame = b"panel"
        subject.panel_camera_source_ts = 1.0
        subject.overview_camera_frame = b"overview"
        subject.overview_camera_source_ts = 1.0
        subject._camera_cb = lambda _msg: None
        subject._ai_camera_cb = lambda _msg: None
        updates = {}
        subject._set = lambda key, value: updates.__setitem__(key, value)

        subject._camera_subscription_tick()
        self.assertEqual(
            [subscription[1] for subscription in subject.node.created],
            ["/camera/image_raw/compressed"],
        )
        raw_subscription = subject.camera_subscription
        subject._camera_subscription_tick()
        self.assertEqual(len(subject.node.created), 1)

        subject.data["camera_frame"] = {"value": b"frame", "ts": time.time()}
        subject.camera_clients.is_active = False
        subject._camera_subscription_tick()

        self.assertIsNone(subject.camera_subscription)
        self.assertEqual(subject.node.destroyed, [raw_subscription])
        self.assertNotIn("camera_frame", subject.data)
        self.assertIsNone(subject.panel_camera_frame)
        self.assertIsNone(subject.overview_camera_frame)
        self.assertFalse(updates["camera_info"]["streaming"])
        self.assertEqual(updates["camera_info"]["publisher_count"], 1)
        self.assertEqual(updates["camera_info"]["bytes"], 4321)

    def test_annotated_subscription_requires_object_mode_and_demand(self):
        subject_type = load_method(
            "_camera_subscription_tick",
            {
                "time": time,
                "CompressedImage": object(),
                "qos_profile_sensor_data": object(),
                "CAMERA_HEALTH_PERIOD_SECONDS": 1.0,
            },
        )
        subject = subject_type()
        subject.node = FakeNode()
        subject.camera_clients = FakeDemand(True)
        subject.ai_mode = "object"
        subject.camera_subscription = None
        subject.ai_camera_subscription = None
        subject.last_camera_health = 0.0
        subject.last_camera_bytes = 0
        subject.prev_motion_gray = None
        subject.lock = threading.Lock()
        subject.camera_frame_condition = threading.Condition(subject.lock)
        subject.data = {}
        subject.panel_camera_frame = None
        subject.panel_camera_source_ts = 0.0
        subject.overview_camera_frame = None
        subject.overview_camera_source_ts = 0.0
        subject._camera_cb = lambda _msg: None
        subject._ai_camera_cb = lambda _msg: None
        subject._set = lambda *_args: None

        subject._camera_subscription_tick()
        self.assertEqual(
            [subscription[1] for subscription in subject.node.created],
            [
                "/camera/image_raw/compressed",
                "/camera/detections/compressed",
            ],
        )
        self.assertEqual(subject.node.created[1][3], 10)

        annotated_subscription = subject.ai_camera_subscription
        subject.ai_mode = "eco"
        subject._camera_subscription_tick()
        self.assertIsNone(subject.ai_camera_subscription)
        self.assertIn(annotated_subscription, subject.node.destroyed)
        self.assertIsNotNone(subject.camera_subscription)

    def test_idle_graph_health_fails_closed_without_a_publisher(self):
        subject_type = load_method(
            "_camera_subscription_tick",
            {
                "time": time,
                "CompressedImage": object(),
                "qos_profile_sensor_data": object(),
                "CAMERA_HEALTH_PERIOD_SECONDS": 1.0,
            },
        )
        subject = subject_type()
        subject.node = FakeNode(publishers=0)
        subject.camera_clients = FakeDemand(False)
        subject.ai_mode = "eco"
        subject.camera_subscription = None
        subject.ai_camera_subscription = None
        subject.last_camera_health = 0.0
        subject.last_camera_bytes = 4321
        subject.prev_motion_gray = None
        subject.lock = threading.Lock()
        subject.camera_frame_condition = threading.Condition(subject.lock)
        subject.data = {}
        subject.panel_camera_frame = None
        subject.panel_camera_source_ts = 0.0
        subject.overview_camera_frame = None
        subject.overview_camera_source_ts = 0.0
        updates = {}
        subject._set = lambda key, value: updates.__setitem__(key, value)

        subject._camera_subscription_tick()

        self.assertEqual(subject.last_camera_bytes, 0)
        self.assertEqual(updates["camera_info"]["publisher_count"], 0)
        self.assertEqual(updates["camera_info"]["bytes"], 0)

    def test_spin_has_no_permanent_jpeg_subscription(self):
        rendered = ast.unparse(method_node("AtlasRosNode", "_spin"))
        self.assertNotIn('"/camera/image_raw/compressed"', rendered)
        self.assertNotIn('"/camera/detections/compressed"', rendered)


if __name__ == "__main__":
    unittest.main()
