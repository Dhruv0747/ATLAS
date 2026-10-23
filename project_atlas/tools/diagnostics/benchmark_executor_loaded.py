"""PC-only fixed-work ROS benchmark, alternating paired candidates; no ATLAS I/O."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import time

import benchmark_executor_counts as B


def summarize(rows):
    pairs = {}
    for row in rows:
        if row['sent'] != row['received'] or row['errors']:
            raise ValueError('message integrity failed')
        if row['cpu_s'] <= 0 or not math.isfinite(row['cpu_s']):
            raise ValueError('invalid CPU measurement')
        pair = pairs.setdefault(row['pair'], {})
        if row['variant'] in pair:
            raise ValueError('duplicate pair variant')
        pair[row['variant']] = row
    savings = []
    for pair in pairs.values():
        if set(pair) != {'cancellation_only', 'combined'}:
            raise ValueError('incomplete pair')
        a, b = pair['cancellation_only'], pair['combined']
        if a['sent'] != b['sent']:
            raise ValueError('unequal work')
        savings.append(100 * (1 - b['cpu_s'] / a['cpu_s']))
    if not savings:
        raise ValueError('no pairs')
    return dict(pairs=len(savings), paired_cpu_saving_percent=savings,
                median_saving_percent=statistics.median(savings),
                min_saving_percent=min(savings), max_saving_percent=max(savings),
                positive_pairs=sum(x > 0 for x in savings),
                scope='PC fixed-work process CPU, not whole Jetson savings')


def run_case(module, pair, variant, rounds):
    import rclpy
    from rclpy.context import Context
    from std_msgs.msg import Int32
    ctx = Context()
    rclpy.init(context=ctx)
    node = rclpy.create_node('atlas_offline_loaded', context=ctx)
    executor = module.SingleThreadedExecutor(context=ctx)
    executor.add_node(node)
    seen, pending, latency, errors = {}, {}, [], []
    timer_count = [0]

    def receive(index, value):
        key = index, value
        if key not in pending or value <= seen.get(index, -1):
            errors.append('duplicate, unordered or unexpected message')
            return
        latency.append(time.monotonic_ns() - pending.pop(key))
        seen[index] = value

    subscriptions = [node.create_subscription(Int32, '/offline/loaded_' + str(i),
        lambda m, i=i: receive(i, m.data), 10) for i in range(107)]
    publishers = [node.create_publisher(Int32, '/offline/loaded_' + str(i), 10) for i in range(107)]
    timer = node.create_timer(.01, lambda: timer_count.__setitem__(0, timer_count[0] + 1))
    try:
        deadline = time.monotonic() + 5
        while not all(pub.get_subscription_count() == 1 for pub in publishers):
            if time.monotonic() > deadline:
                raise RuntimeError('local discovery timeout')
            executor.spin_once(timeout_sec=.01)
        for sequence in range(-5, 0):
            # Untimed warmup via executor callbacks, not measured message stream.
            executor.create_task(lambda: None)
            executor.spin_once(timeout_sec=0)
        start_cpu, start_wall = time.process_time(), time.monotonic()
        cancelled = []
        for seq in range(rounds):
            if seq % 5 == 0:
                task = executor.create_task(lambda: cancelled.append('BAD'))
                task.cancel()
            if seq == rounds // 2:
                extra = node.create_subscription(Int32, '/offline/extra', lambda m: None, 10)
                node.destroy_subscription(extra)
            for i, pub in enumerate(publishers):
                pending[i, seq] = time.monotonic_ns()
                pub.publish(Int32(data=seq))
            deadline = time.monotonic() + 3
            while pending:
                if time.monotonic() > deadline:
                    raise RuntimeError('loaded message timeout')
                executor.spin_once(timeout_sec=.01)
        cpu, wall = time.process_time() - start_cpu, time.monotonic() - start_wall
        if cancelled:
            errors.append('cancelled callback executed')
        ordered = sorted(latency)
        if not timer_count[0]:
            errors.append('timer starved')
        return dict(pair=pair, variant=variant, cpu_s=cpu, wall_s=wall,
            one_core_cpu_percent=100*cpu/wall, sent=107*rounds, received=len(latency),
            errors=errors, latency_p95_ms=ordered[math.ceil(.95*len(ordered))-1]/1e6,
            latency_max_ms=max(ordered)/1e6, timer_callbacks=timer_count[0],
            cancellation_checks=len(range(0, rounds, 5)), dynamic_add_remove=True)
    finally:
        assert executor.shutdown(timeout_sec=1)
        node.destroy_node()
        ctx.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--pairs', type=int, default=6)
    parser.add_argument('--rounds', type=int, default=1000)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('ROS_LOCALHOST_ONLY') != '1' or os.environ.get('ROS_DOMAIN_ID') != '213':
        raise RuntimeError('isolated PC localhost domain213 required')
    if not 2 <= args.pairs <= 10 or not 10 <= args.rounds <= 2000:
        raise ValueError('bounded workload required')
    raw = args.source.read_bytes()
    sources = {name: B.cancellation_candidate(raw, optimized) for name, optimized in
               [('cancellation_only', False), ('combined', True)]}
    modules = {name: B.load_executor(source, name) for name, source in sources.items()}
    rows = []
    for pair in range(args.pairs):
        order = ['cancellation_only', 'combined']
        if pair % 2:
            order.reverse()
        for variant in order:
            row = run_case(modules[variant], pair, variant, args.rounds)
            rows.append(row)
            print(json.dumps(row), flush=True)
    report = dict(source_sha256=hashlib.sha256(raw).hexdigest(),
                  candidate_hashes={k: hashlib.sha256(v.encode()).hexdigest() for k,v in sources.items()},
                  rows=rows, summary=summarize(rows), deployment='NONE')
    with args.output.open('x') as output:
        json.dump(report, output, indent=2)
    print(json.dumps(report['summary'], indent=2))


if __name__ == '__main__':
    main()
