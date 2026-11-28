"""Opt-in batched spinning for monitoring/status nodes (2026-11-13).

The 2026-11-13 CPU profile (tools/profiling/atlas_cpu_profile.py) showed small rclpy nodes at 13-17 % of a core each
at only ~60 incoming messages/s: rclpy's SingleThreadedExecutor rebuilds its whole wait set for every message.
Sleeping batch_s before each wait lets every message that arrived meanwhile be dispatched in one pass (same trick
as atlas_dashboard_executor, which cut rover-status-web from ~40 % to ~17 %), at the cost of up to batch_s latency.

Behaviour is unchanged unless ATLAS_EXECUTOR_BATCH_S is set (> 0) in the unit's environment, so a systemd
drop-in enables it per service and deleting the drop-in reverts it. Not for motor, mux or other stop-path nodes.
"""
import os
import time

MAX_BATCH_S = 0.2


def batch_from_env(default: float = 0.0) -> float:
    try:
        value = float(os.environ.get("ATLAS_EXECUTOR_BATCH_S", default))
    except ValueError:
        return 0.0
    return min(max(value, 0.0), MAX_BATCH_S)


def make_batched(executor, batch_s: float):
    if batch_s <= 0:
        return executor
    inner = executor._wait_for_ready_callbacks

    def wait_batched(*args, **kwargs):
        time.sleep(batch_s)
        # A systemctl stop during the sleep invalidates the context; report it as the normal shutdown signal
        # instead of letting the wait-set rebuild raise RCLError ("context is not valid") as a crash.
        context = getattr(executor, "_context", None)
        if context is not None and not context.ok():
            from rclpy.executors import ExternalShutdownException
            raise ExternalShutdownException()
        yield from inner(*args, **kwargs)

    executor._wait_for_ready_callbacks = wait_batched
    return executor


def spin(node, batch_s=None):
    """Drop-in for rclpy.spin(node); batches only when configured."""
    import rclpy
    from rclpy.executors import SingleThreadedExecutor

    batch_s = batch_from_env() if batch_s is None else min(max(float(batch_s), 0.0), MAX_BATCH_S)
    if batch_s <= 0:
        rclpy.spin(node)
        return
    executor = make_batched(SingleThreadedExecutor(context=node.context), batch_s)
    node.get_logger().info(f"batched executor: {batch_s * 1000:.0f} ms")
    try:
        rclpy.spin(node, executor=executor)
    except Exception as exc:
        # Same race, narrowed: shutdown landing between the context check and the wait-set build.
        if node.context.ok() or type(exc).__name__ not in ("RCLError", "ExternalShutdownException"):
            raise
        from rclpy.executors import ExternalShutdownException
        raise ExternalShutdownException() from None
    finally:
        executor.shutdown(timeout_sec=1)
