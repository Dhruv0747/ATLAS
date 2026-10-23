"""Opt-in PC localhost ROS tests. No production endpoints or hardware."""
import importlib.util
import os
from pathlib import Path
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bench', ROOT/'tools/diagnostics/benchmark_executor_counts.py')
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)


class QosShutdownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get('ROS_LOCALHOST_ONLY') != '1' or os.environ.get('ROS_DOMAIN_ID') != '213':
            raise unittest.SkipTest('isolated PC ROS domain213 required')
        path = os.environ.get('ATLAS_CAPTURED_EXECUTOR')
        if not path:
            raise unittest.SkipTest('captured source required')
        cls.raw = Path(path).read_bytes()

    def exercise(self, scenario):
        import rclpy
        from rclpy.context import Context
        from rclpy.duration import Duration
        from rclpy.qos import QoSProfile, ReliabilityPolicy
        from rclpy.qos_event import SubscriptionEventCallbacks
        from std_msgs.msg import Int32
        for optimized in (False, True):
            with self.subTest(combined=optimized):
                module = B.load_executor(B.cancellation_candidate(self.raw, optimized), 'offline_qos')
                context = Context()
                rclpy.init(context=context)
                node = rclpy.create_node('offline_qos_shutdown', context=context)
                executor = module.SingleThreadedExecutor(context=context)
                executor.add_node(node)
                threads, errors = [], []
                release = threading.Event()

                def spin():
                    try:
                        executor.spin()
                    except (module.ExternalShutdownException, module.ShutdownException):
                        pass
                    except Exception as exc:
                        errors.append(repr(exc))

                def start_spin():
                    thread = threading.Thread(target=spin, daemon=True)
                    threads.append(thread)
                    thread.start()

                try:
                    if scenario == 'incompatible':
                        events, received = [], []
                        node.create_subscription(Int32, '/offline/qos', lambda m: received.append(m.data),
                            QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE),
                            event_callbacks=SubscriptionEventCallbacks(incompatible_qos=lambda e: events.append(e.total_count)))
                        pub = node.create_publisher(Int32, '/offline/qos',
                            QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT))
                        end = time.monotonic() + 3
                        while not events and time.monotonic() < end:
                            pub.publish(Int32(data=1))
                            executor.spin_once(timeout_sec=.02)
                        self.assertTrue(events, 'incompatible QoS event missing')
                        self.assertFalse(received)
                    elif scenario == 'deadline':
                        events, received = [], []
                        qos = QoSProfile(depth=10, deadline=Duration(seconds=.05))
                        node.create_subscription(Int32, '/offline/deadline', lambda m: received.append(m.data), qos,
                            event_callbacks=SubscriptionEventCallbacks(deadline=lambda e: events.append(e.total_count)))
                        pub = node.create_publisher(Int32, '/offline/deadline', qos)
                        end = time.monotonic() + 3
                        while not received and time.monotonic() < end:
                            pub.publish(Int32(data=7))
                            executor.spin_once(timeout_sec=.01)
                        self.assertTrue(received)
                        end = time.monotonic() + 2
                        while not events and time.monotonic() < end:
                            executor.spin_once(timeout_sec=.02)
                        self.assertTrue(events, 'deadline event missing')
                    elif scenario == 'blocked_callback':
                        entered, finished = threading.Event(), threading.Event()
                        def callback():
                            entered.set()
                            if not release.wait(2):
                                errors.append('callback release timeout')
                            finished.set()
                        timer = node.create_timer(.001, callback)
                        start_spin()
                        self.assertTrue(entered.wait(1))
                        self.assertFalse(executor.shutdown(timeout_sec=.02), 'shutdown must not report completion while callback runs')
                        release.set()
                        self.assertTrue(finished.wait(1))
                    elif scenario == 'context_shutdown':
                        start_spin()
                        time.sleep(.02)
                        context.shutdown()
                    elif scenario == 'dynamic_entities':
                        seen = threading.Event()
                        start_spin()
                        for i in range(30):
                            sub = node.create_subscription(Int32, '/offline/transient_'+str(i), lambda m: None, 10)
                            node.destroy_subscription(sub)
                        sub = node.create_subscription(Int32, '/offline/healthy', lambda m: seen.set(), 10)
                        pub = node.create_publisher(Int32, '/offline/healthy', 10)
                        end = time.monotonic() + 2
                        while not seen.is_set() and time.monotonic() < end:
                            pub.publish(Int32(data=1))
                            seen.wait(.01)
                        self.assertTrue(seen.is_set(), 'no callback after entity churn')
                    else:
                        raise ValueError(scenario)
                finally:
                    release.set()
                    executor.shutdown(timeout_sec=1)
                    for thread in threads:
                        thread.join(1)
                        self.assertFalse(thread.is_alive(), 'orphan executor thread')
                    node.destroy_node()
                    if context.ok():
                        context.shutdown()
                self.assertEqual(errors, [])

    def test_incompatible_qos_event(self): self.exercise('incompatible')
    def test_deadline_event(self): self.exercise('deadline')
    def test_shutdown_during_callback(self): self.exercise('blocked_callback')
    def test_context_shutdown_while_waiting(self): self.exercise('context_shutdown')
    def test_entity_churn_while_spinning(self): self.exercise('dynamic_entities')
