import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools/diagnostics'))
import prepare_dashboard_executor_package as P


class PackageTests(unittest.TestCase):
    def adapter(self):
        spec = importlib.util.spec_from_file_location('adapter_test', ROOT/'scripts/atlas_dashboard_executor.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_baseline_mismatch_rejected(self):
        with self.assertRaises(ValueError): P.patch_web(b'wrong baseline')

    def test_exact_live_byte_reversal(self):
        path = os.environ.get('ATLAS_CAPTURED_WEB')
        if not path: self.skipTest('captured exact live file required')
        raw = Path(path).read_bytes()
        result = P.patch_web(raw).decode()
        for old, new in reversed(P.REPLACEMENTS): result = result.replace(new, old)
        self.assertEqual(result.encode(), raw)

    def test_overlay_hash_mismatch_rejected(self):
        m = self.adapter()
        with patch.object(Path, 'read_bytes', return_value=b'wrong overlay'):
            with self.assertRaises(RuntimeError): m.create_executor()
        self.assertIsNone(m._module)

    def test_spin_cleanup_on_exception(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        m = self.adapter()
        executor = Mock()
        fake_ros = SimpleNamespace(spin=Mock(side_effect=ValueError('callback error')))
        with patch.object(m, 'create_executor', return_value=executor), patch.dict(sys.modules, {'rclpy': fake_ros}):
            with self.assertRaises(ValueError): m.spin(SimpleNamespace(context='private'))
        executor.shutdown.assert_called_once_with(timeout_sec=1)

    def test_no_global_executor_replacement(self):
        text = (ROOT/'scripts/atlas_dashboard_executor.py').read_text()
        self.assertNotIn('rclpy.executors =', text)
        self.assertNotIn('get_global_executor', text)
        self.assertNotIn('sys.modules[', text)

    def test_packaged_native_loader(self):
        directory = os.environ.get('ATLAS_EXECUTOR_PACKAGE')
        if not directory or os.environ.get('ROS_DOMAIN_ID') != '213' or os.environ.get('ROS_LOCALHOST_ONLY') != '1':
            self.skipTest('isolated PC package run required')
        import rclpy
        import rclpy.executors
        from rclpy.context import Context
        original_class = rclpy.executors.SingleThreadedExecutor
        spec = importlib.util.spec_from_file_location('packaged_adapter', Path(directory)/'atlas_dashboard_executor.py')
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        ctx = Context()
        rclpy.init(context=ctx)
        executor = m.create_executor(context=ctx)
        seen = []
        try:
            cancelled = executor.create_task(lambda: seen.append('BAD'))
            cancelled.cancel()
            executor.create_task(lambda: seen.append('OK'))
            for _ in range(5): executor.spin_once(timeout_sec=0)
            self.assertEqual(seen, ['OK'])
            self.assertIs(rclpy.executors.SingleThreadedExecutor, original_class)
            self.assertIsNot(type(executor), original_class)
        finally:
            self.assertTrue(executor.shutdown(timeout_sec=1))
            ctx.shutdown()

    def test_copy_install_and_rollback_rehearsal(self):
        directory = os.environ.get('ATLAS_EXECUTOR_PACKAGE')
        if not directory: self.skipTest('prepared PC package required')
        import hashlib
        import json
        import shutil
        source = Path(directory)
        manifest = json.loads((source/'manifest.json').read_text())
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            shutil.copyfile(source/'atlas_status_web.original', target/'atlas_status_web.py')
            original = (target/'atlas_status_web.py').read_bytes()
            self.assertEqual(hashlib.sha256(original).hexdigest(), manifest['baseline_sha256'])
            for name, digest in manifest['files'].items():
                shutil.copyfile(source/name, target/name)
                self.assertEqual(hashlib.sha256((target/name).read_bytes()).hexdigest(), digest)
            shutil.copyfile(source/'atlas_status_web.original', target/'atlas_status_web.py')
            for name in ('atlas_dashboard_executor.py', 'atlas_dashboard_executor_impl.py'):
                (target/name).unlink()
            self.assertEqual((target/'atlas_status_web.py').read_bytes(), original)
            self.assertEqual([p.name for p in target.iterdir()], ['atlas_status_web.py'])
