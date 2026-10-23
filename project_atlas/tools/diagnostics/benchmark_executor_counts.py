"""PC-only exact-source candidate benchmark; never installs or contacts ATLAS.

Candidate replaces one count-addition expression, not executor scheduling.
Use --ros only on an isolated PC with ROS_LOCALHOST_ONLY=1 and ROS_DOMAIN_ID=213.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import statistics
import time

SOURCE_SHA = 'e854591961c38e95e465c2040400c18111b8b3ce445cae195345cabbaaf6c010'
FIELDS = ('num_subscriptions', 'num_guard_conditions', 'num_timers',
          'num_clients', 'num_services', 'num_events')
OLD = '                        entity_count += waitable.get_num_entities()'
NEW = ('                        added_count = waitable.get_num_entities()\n'
       '                        entity_count = NumberOfEntities(\n' +
       ''.join('                            entity_count.' + f + ' + added_count.' + f + ',\n'
               for f in FIELDS) + '                        )')


def candidate(source_bytes):
    if hashlib.sha256(source_bytes).hexdigest() != SOURCE_SHA:
        raise ValueError('exact installed source hash required')
    source = source_bytes.decode()
    if source.count(OLD) != 1:
        raise ValueError('ambiguous count addition')
    result = source.replace(OLD, NEW)
    compile(result, '<offline-candidate>', 'exec')
    return result


def count_class(source):
    """Extract actual NumberOfEntities only, without importing ROS or opening DDS."""
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'NumberOfEntities')
    scope = {}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), '<captured-waitable>', 'exec'), scope)
    return scope['NumberOfEntities']


def add_direct(cls, left, right):
    return cls(left.num_subscriptions + right.num_subscriptions,
               left.num_guard_conditions + right.num_guard_conditions,
               left.num_timers + right.num_timers,
               left.num_clients + right.num_clients,
               left.num_services + right.num_services,
               left.num_events + right.num_events)


def microbench(cls, iterations=3000):
    results = {}
    for count in (21, 82, 107):
        additions = [cls(num_events=1) for _ in range(count)]
        durations = {'original': [], 'candidate': []}
        for repeat in range(8):
            # Alternate order, same objects, same sum; no microsecond wall-clock claims.
            for mode in (('original', 'candidate') if repeat % 2 == 0 else ('candidate', 'original')):
                start = time.process_time_ns()
                for _ in range(iterations):
                    total = cls()
                    for added in additions:
                        total = total + added if mode == 'original' else add_direct(cls, total, added)
                durations[mode].append((time.process_time_ns() - start) / iterations / 1000)
                assert total.num_events == count
        medians = {k: statistics.median(v) for k, v in durations.items()}
        results[str(count)] = {'cpu_us_per_counting_pass': medians,
                              'reduction_percent': 100 * (1 - medians['candidate'] / medians['original'])}
    return results


def load_executor(source, name):
    import types
    module = types.ModuleType(name)
    exec(compile(source, '<' + name + '>', 'exec'), module.__dict__)
    return module


def native_suite(original, optimized, reverse=False):
    if os.environ.get('ROS_LOCALHOST_ONLY') != '1' or os.environ.get('ROS_DOMAIN_ID') != '213':
        raise RuntimeError('PC isolated localhost domain213 required')
    import rclpy
    from rclpy.context import Context
    from std_msgs.msg import Int32
    result = {}
    cases = [('original', original), ('candidate', optimized)]
    for label, source in (list(reversed(cases)) if reverse else cases):
        module = load_executor(source, 'atlas_offline_' + label)
        ctx = Context()
        rclpy.init(context=ctx)
        node = rclpy.create_node('offline_count_benchmark', context=ctx)
        executor = module.SingleThreadedExecutor(context=ctx)
        executor.add_node(node)
        received = []
        subscriptions = [node.create_subscription(Int32, '/offline/count_' + str(i),
                         lambda m: received.append(m.data), 10) for i in range(107)]
        publisher = node.create_publisher(Int32, '/offline/count_0', 10)
        try:
            for _ in range(10):
                executor.spin_once(timeout_sec=0)
            timing = []
            for _ in range(5):
                start = time.process_time_ns()
                for _ in range(300):
                    executor.spin_once(timeout_sec=0)
                timing.append((time.process_time_ns() - start) / 300 / 1000)
            for value in range(10):
                publisher.publish(Int32(data=value))
                deadline = time.monotonic() + 2
                while value not in received and time.monotonic() < deadline:
                    executor.spin_once(timeout_sec=.01)
                assert received[-1:] == [value], received
            assert received == list(range(10)), received
            node.destroy_subscription(subscriptions.pop())
            dynamic = node.create_subscription(Int32, '/offline/dynamic', lambda m: received.append(m.data), 10)
            pub2 = node.create_publisher(Int32, '/offline/dynamic', 10)
            pub2.publish(Int32(data=123))
            deadline = time.monotonic() + 2
            while 123 not in received and time.monotonic() < deadline:
                executor.spin_once(timeout_sec=.01)
            assert 123 in received
            node.destroy_subscription(dynamic)
            task = executor.create_task(lambda: (_ for _ in ()).throw(RuntimeError('test callback')))
            caught = False
            try:
                executor.spin_once(timeout_sec=0)
            except RuntimeError as exc:
                caught = str(exc) == 'test callback'
            assert caught
            cancelled = []
            task = executor.create_task(lambda: cancelled.append(True))
            task.cancel()
            cancellation_error = None
            try:
                for _ in range(3):
                    executor.spin_once(timeout_sec=0)
            except KeyError:
                cancellation_error = 'KeyError in ready-task lookup (baseline defect)'
            assert not cancelled
            result[label] = dict(idle_spin_cpu_us=statistics.median(timing),
                subscriptions=107, ordered_messages=10, dynamic_add_remove=True,
                callback_exception=True, cancelled_callback_not_run=True,
                task_cancellation_error=cancellation_error)
        finally:
            assert executor.shutdown(timeout_sec=1), 'executor shutdown timed out'
            node.destroy_node()
            ctx.shutdown()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executor', type=Path)
    parser.add_argument('waitable', type=Path)
    parser.add_argument('--ros', action='store_true')
    parser.add_argument('--reverse', action='store_true', help='counterbalance native case order')
    args = parser.parse_args()
    original = args.executor.read_bytes()
    optimized = candidate(original)
    report = {'source_sha256': hashlib.sha256(original).hexdigest(),
              'candidate_sha256': hashlib.sha256(optimized.encode()).hexdigest(),
              'microbenchmark': microbench(count_class(args.waitable.read_text())),
              'deployment': 'NONE; PC experiment, not Jetson CPU savings'}
    if args.ros:
        report['native_ros'] = native_suite(original.decode(), optimized, args.reverse)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
