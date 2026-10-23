"""Explicit PC native tests: captured source required, localhost domain213 only."""
import importlib.util
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('count_bench', ROOT/'tools/diagnostics/benchmark_executor_counts.py')
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)


class CancellationNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get('ROS_LOCALHOST_ONLY') != '1' or os.environ.get('ROS_DOMAIN_ID') != '213':
            raise unittest.SkipTest('requires explicit isolated PC ROS environment')
        path = os.environ.get('ATLAS_CAPTURED_EXECUTOR')
        if not path:
            raise unittest.SkipTest('requires captured source path')
        cls.source = Path(path).read_bytes()
        B.candidate(cls.source)  # fail on wrong hash, not silent skip

    def exercise(self, kind, fixed):
        import rclpy
        from rclpy.context import Context
        from rclpy.task import Future
        source = B.cancellation_candidate(self.source, True) if fixed else self.source.decode()
        module = B.load_executor(source, 'cancel_test')
        ctx = Context()
        rclpy.init(context=ctx)
        executor = module.SingleThreadedExecutor(context=ctx)
        seen = []
        try:
            if kind in ('cancel', 'done', 'exception'):
                task = executor.create_task(lambda: seen.append('BAD'))
                if kind == 'cancel':
                    task.cancel()
                elif kind == 'done':
                    task.set_result('already done')
                else:
                    task.set_exception(ValueError('already failed'))
                    self.assertIsInstance(task.exception(), ValueError)
            elif kind == 'resume':
                future = Future(executor=executor)
                async def pending():
                    seen.append('entered')
                    await future
                    seen.append('BAD')
                task = executor.create_task(pending)
                executor.spin_once(timeout_sec=0)
                self.assertEqual(seen, ['entered'])
                task.cancel()
                future.set_result(1)
            elif kind == 'duplicate_done':
                task = executor.create_task(lambda: seen.append('once'))
                executor.spin_once(timeout_sec=0)
                executor._call_task_in_next_spin(task)
            elif kind == 'burst':
                for i in range(200):
                    task = executor.create_task(lambda i=i: seen.append(i))
                    if i % 2 == 0:
                        task.cancel()
            executor.create_task(lambda: seen.append('healthy'))
            failure = None
            try:
                for _ in range(220 if kind == 'burst' else 12):
                    executor.spin_once(timeout_sec=0)
            except KeyError:
                failure = 'KeyError'
            if fixed:
                self.assertIsNone(failure)
                self.assertNotIn('BAD', seen)
                self.assertIn('healthy', seen)
                if kind == 'burst':
                    self.assertEqual([v for v in seen if isinstance(v, int)], list(range(1, 200, 2)))
                if kind == 'duplicate_done':
                    self.assertEqual(seen.count('once'), 1)
            else:
                self.assertEqual(failure, 'KeyError')
        finally:
            self.assertTrue(executor.shutdown(timeout_sec=1))
            ctx.shutdown()

    def test_original_reproduces_cancel_error(self):
        self.exercise('cancel', False)

    def test_original_reproduces_done_error(self):
        self.exercise('done', False)

    def test_fixed_cancel(self):
        self.exercise('cancel', True)

    def test_fixed_done(self):
        self.exercise('done', True)

    def test_fixed_exception_done(self):
        self.exercise('exception', True)

    def test_fixed_cancelled_coroutine_resumed_by_future(self):
        self.exercise('resume', True)

    def test_fixed_completed_task_requeued(self):
        self.exercise('duplicate_done', True)

    def test_fixed_mixed_burst(self):
        self.exercise('burst', True)

    def test_wrong_source_rejected(self):
        with self.assertRaises(ValueError):
            B.cancellation_candidate(b'changed')
