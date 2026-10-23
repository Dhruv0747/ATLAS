"""Opt-in Dashboard-only executor adapter. Does not modify global rclpy state."""
import hashlib
from pathlib import Path
import threading
import types

OVERLAY_SHA = '543e41125a6095ba5a69f114deaa2dc4cf54c4df2029f78fdb80c99ecf81b5c1'
_lock = threading.Lock()
_module = None


def create_executor(**kwargs):
    global _module
    with _lock:
        if _module is None:
            path = Path(__file__).with_name('atlas_dashboard_executor_impl.py')
            source = path.read_bytes()
            if hashlib.sha256(source).hexdigest() != OVERLAY_SHA:
                raise RuntimeError('Dashboard executor overlay integrity mismatch')
            module = types.ModuleType('atlas_private_dashboard_executor')
            module.__file__ = str(path)
            exec(compile(source, str(path), 'exec'), module.__dict__)
            _module = module
        executor_class = _module.SingleThreadedExecutor
    return executor_class(**kwargs)


def spin(node):
    import rclpy
    executor = create_executor(context=node.context)
    try:
        rclpy.spin(node, executor=executor)
    finally:
        executor.shutdown(timeout_sec=1)
