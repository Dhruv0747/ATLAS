"""Opt-in Dashboard-only executor adapter. Does not modify global rclpy state."""
import hashlib
from pathlib import Path
import threading
import types

OVERLAY_SHA = '4f5c1cc92c3ed156d68e0663639396be0c01f3d8b71c15f4fb4a98ea6521d9a8'
_lock = threading.Lock()
_module = None


def _batched(executor, batch_s):
    """2026-11-13: wait batch_s before each wait-set rebuild so every message that arrived meanwhile is
    dispatched in one pass (the executor otherwise rebuilds its wait set per message: ~190/s, ~40 % of a core)."""
    if not batch_s or batch_s <= 0:
        return executor
    import time
    inner = executor._wait_for_ready_callbacks

    def wait_batched(*args, **kwargs):
        time.sleep(batch_s)
        yield from inner(*args, **kwargs)
    executor._wait_for_ready_callbacks = wait_batched
    return executor


def create_executor(batch_s=0.0, **kwargs):
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
    return _batched(executor_class(**kwargs), batch_s)


def spin(node, batch_s=0.0):
    import rclpy
    executor = create_executor(batch_s=batch_s, context=node.context)
    try:
        rclpy.spin(node, executor=executor)
    finally:
        executor.shutdown(timeout_sec=1)
