"""Stage31 offline gates: Astra driver and Vision Lab receiver share a PRIVATE ROS domain. No ROS, camera or service."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import atlas_vision3d_runtime as R   # noqa: E402
import atlas_vision3d_web as W       # noqa: E402

SRC_R = (Path(__file__).resolve().parents[1] / 'scripts/atlas_vision3d_runtime.py').read_text()
SRC_W = (Path(__file__).resolve().parents[1] / 'scripts/atlas_vision3d_web.py').read_text()


def fake_rclpy(record):
    rclpy = ModuleType('rclpy')
    rclpy.init = lambda **kw: record.setdefault('init', []).append(kw)
    node = MagicMock(); node.get_topic_names_and_types.return_value = [
        ('/astra/depth/image_raw', ['sensor_msgs/msg/Image']), ('/astra/color/camera_info', ['sensor_msgs/msg/CameraInfo'])]
    node.create_subscription.side_effect = lambda typ, topic, cb, qos: record.setdefault('subs', []).append((typ.__name__, topic))
    rclpy.create_node = lambda name, context=None: node
    ctx = ModuleType('rclpy.context'); ctx.Context = MagicMock
    ex = ModuleType('rclpy.executors'); ex.SingleThreadedExecutor = MagicMock
    qos = ModuleType('rclpy.qos'); qos.QoSProfile = lambda **k: k
    qos.ReliabilityPolicy = SimpleNamespace(BEST_EFFORT=1); qos.DurabilityPolicy = SimpleNamespace(VOLATILE=1)
    msgs = ModuleType('sensor_msgs.msg')
    for n in ('Image', 'CameraInfo', 'PointCloud2'):
        setattr(msgs, n, type(n, (), {}))
    sm = ModuleType('sensor_msgs'); sm.msg = msgs
    return {'rclpy': rclpy, 'rclpy.context': ctx, 'rclpy.executors': ex, 'rclpy.qos': qos, 'sensor_msgs': sm, 'sensor_msgs.msg': msgs}


class PrivateDomain(unittest.TestCase):
    def test_domain_is_private_and_not_production(self):
        self.assertIsInstance(R.ISOLATED_DOMAIN_ID, int)
        self.assertNotEqual(R.ISOLATED_DOMAIN_ID, 0)
        self.assertTrue(1 <= R.ISOLATED_DOMAIN_ID <= 101)          # valid FastDDS port range

    def test_driver_env_sets_private_domain_and_keeps_thread_limits(self):
        env = R.driver_env({'PATH': '/bin', 'ROS_DOMAIN_ID': '0'})
        self.assertEqual(env['ROS_DOMAIN_ID'], str(R.ISOLATED_DOMAIN_ID))
        self.assertEqual((env['OPENBLAS_NUM_THREADS'], env['OMP_NUM_THREADS']), ('1', '1'))
        self.assertEqual(env['PATH'], '/bin')

    def test_worker_launches_driver_with_driver_env_only(self):
        self.assertIn('env=driver_env(os.environ)', SRC_R)
        self.assertEqual(SRC_R.count("env['ROS_DOMAIN_ID']="), 1)   # set in exactly one place, for the camera child

    def test_domain_in_use_detects_existing_owner_and_ignores_unreadable(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / '10').mkdir(); (root / '10/environ').write_bytes(b'PATH=/bin\0ROS_DOMAIN_ID=0\0')
            (root / '11').mkdir()                                  # unreadable/missing environ
            (root / 'self').mkdir()
            self.assertFalse(R.domain_in_use(R.ISOLATED_DOMAIN_ID, root))
            (root / '12').mkdir(); (root / '12/environ').write_bytes(b'ROS_DOMAIN_ID=%d\0' % R.ISOLATED_DOMAIN_ID)
            self.assertTrue(R.domain_in_use(R.ISOLATED_DOMAIN_ID, root))
            (root / '13').mkdir(); (root / '13/environ').write_bytes(b'ROS_DOMAIN_ID=%d7\0' % R.ISOLATED_DOMAIN_ID)
            (root / '12/environ').write_bytes(b'')
            self.assertFalse(R.domain_in_use(R.ISOLATED_DOMAIN_ID, root))   # 777 is not 77

    def test_collision_check_runs_before_camera_launch(self):
        i_check = SRC_R.index('if domain_in_use(ISOLATED_DOMAIN_ID)')
        i_launch = SRC_R.index('child=subprocess.Popen(driver_args(mode)')
        self.assertLess(i_check, i_launch)

    def test_viewer_receiver_joins_private_domain_not_bridge(self):
        t = W.viewer_transport()
        self.assertIsInstance(t, W.RosTransport)
        self.assertEqual(t.domain_id, R.ISOLATED_DOMAIN_ID)

    def test_receiver_init_passes_domain_and_subscribes_only_manifest_topics(self):
        rec = {}
        with patch.dict(sys.modules, fake_rclpy(rec)), patch.object(W.threading, 'Thread', MagicMock()):
            t = W.RosTransport(domain_id=R.ISOLATED_DOMAIN_ID)
            t.start({'depth': '/astra/depth/image_raw', 'rgb_info': '/astra/color/camera_info',
                     'rgb': '/astra/color/image_raw'}, lambda k, m: None)
        self.assertEqual(rec['init'][0]['domain_id'], R.ISOLATED_DOMAIN_ID)
        self.assertEqual(sorted(rec['subs']), [('CameraInfo', '/astra/color/camera_info'), ('Image', '/astra/depth/image_raw')])

    def test_default_transport_still_uses_default_domain(self):
        rec = {}
        with patch.dict(sys.modules, fake_rclpy(rec)), patch.object(W.threading, 'Thread', MagicMock()):
            W.RosTransport().start({'depth': '/astra/depth/image_raw'}, lambda k, m: None)
        self.assertNotIn('domain_id', rec['init'][0])

    def test_no_publishers_services_or_production_topics_added(self):
        for bad in ('create_publisher', 'create_service', 'create_client', '/cmd_vel', 'estop'):
            self.assertNotIn(bad, SRC_W.lower() if bad == 'estop' else SRC_W)

    def test_policy_thresholds_unchanged(self):
        R.limits(75, 80, 70)
        for v in ((75.01, 50, 60), (50, 80.01, 60), (50, 50, 70.01)):
            with self.assertRaises(ValueError):
                R.limits(*v)
        gate = (Path(__file__).resolve().parents[1] / 'tools/vision3d/stationary_gate.py').read_text()
        self.assertIn('cpu>75', gate); self.assertIn('ram>80', gate); self.assertIn('t>70', gate)


if __name__ == '__main__':
    unittest.main()
