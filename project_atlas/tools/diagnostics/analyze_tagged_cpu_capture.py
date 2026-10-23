"""Offline speedscope/proc correlation; never attaches to a process or controls ROS.

Python thread addresses are deliberately NOT treated as Linux TIDs. CPU derives
only from same-birth /proc tick deltas; sample weights are observations, not CPU.
"""
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path

EXECUTOR_SHA = 'e854591961c38e95e465c2040400c18111b8b3ce445cae195345cabbaaf6c010'


def analyze(profile, events, hz=100, executor_sha=None):
    if not math.isfinite(hz) or hz <= 0:
        raise ValueError('invalid clock tick frequency')
    frames = profile['shared']['frames']
    stacks = []
    for item in profile['profiles']:
        if item['type'] != 'sampled' or item['unit'] != 'seconds':
            raise ValueError('expected sampled seconds profile')
        samples, weights = item['samples'], item['weights']
        if len(samples) != len(weights):
            raise ValueError('sample/weight mismatch')
        leaves = collections.Counter()
        paths = collections.Counter()
        boundary = total = 0.0
        for sample, weight in zip(samples, weights):
            if not math.isfinite(weight) or weight < 0:
                raise ValueError('invalid sample weight')
            total += weight
            if not sample:
                continue
            if any(type(i) is not int or not 0 <= i < len(frames) for i in sample):
                raise ValueError('invalid frame index')
            stack = [frames[i] for i in sample]
            # Count each path once per observation, not once per recursive frame.
            if any(f['name'] == '_wait_for_ready_callbacks' and
                   str(f.get('file', '')).endswith('/rclpy/executors.py') for f in stack):
                paths['executor_wait_set_path_samples'] += 1
            if any(str(f.get('file', '')).endswith('/rclpy/qos_event.py') for f in stack):
                paths['qos_event_path_samples'] += 1
            leaf = frames[sample[-1]]
            if str(leaf.get('file', '')).endswith('/atlas_status_web.py'):
                paths['dashboard_leaf_samples'] += 1
            leaves[(leaf['name'], leaf.get('file'), leaf.get('line'))] += weight
            if (executor_sha == EXECUTOR_SHA and leaf['name'] == '_wait_for_ready_callbacks'
                    and str(leaf.get('file', '')).endswith('/rclpy/executors.py')
                    and leaf.get('line') in (677, 678)):
                boundary += weight
        stacks.append({'python_thread_label': item['name'], 'samples': len(samples),
                       'path_observations': dict(paths),
                       'observed_weight_s': total,
                       'wait_boundary_observation_percent': 100*boundary/total if total else None,
                       'top_leaves': [dict(name=k[0], file=k[1], line=k[2], weight_s=v)
                                      for k, v in leaves.most_common(6)]})
    windows = {}
    previous = None
    for row in events:
        if 'threads' not in row:
            continue
        if previous is not None:
            dt = row['monotonic'] - previous['monotonic']
            if not math.isfinite(dt) or dt <= 0:
                raise ValueError('non-increasing time')
            # Do not mix a transition interval into either measurement window.
            if row['phase'] == previous['phase']:
                phase = windows.setdefault(row['phase'], dict(duration_s=0., cpu_integral=0.,
                    peak_cpu=0., observer_cpu_s=0., threads={}, excluded_thread_intervals=0))
                cpu = row['cpu']
                if not math.isfinite(cpu) or not 0 <= cpu <= 100:
                    raise ValueError('invalid whole CPU')
                phase['duration_s'] += dt
                phase['cpu_integral'] += cpu*dt
                phase['peak_cpu'] = max(phase['peak_cpu'], cpu)
                phase['observer_cpu_s'] += max(0, row['observer_cpu_s']-previous['observer_cpu_s'])
                for tid, after in row['threads'].items():
                    before = previous['threads'].get(tid)
                    if before is None or before['birth'] != after['birth'] or after['ticks'] < before['ticks']:
                        phase['excluded_thread_intervals'] += 1
                        continue
                    thread = phase['threads'].setdefault(tid, dict(cpu_s=0., measured_s=0.))
                    thread['cpu_s'] += (after['ticks']-before['ticks'])/hz
                    thread['measured_s'] += dt
        previous = row
    for phase in windows.values():
        phase['whole_cpu_mean'] = phase.pop('cpu_integral')/phase['duration_s']
        phase['observer_one_core_percent'] = 100*phase['observer_cpu_s']/phase['duration_s']
        for thread in phase['threads'].values():
            thread['one_core_percent'] = 100*thread['cpu_s']/thread['measured_s']
        phase['threads'] = dict(sorted(phase['threads'].items(), key=lambda p: -p[1]['cpu_s']))
    return dict(python_profiles=stacks, windows=windows,
                native_tid_mapping='UNAVAILABLE: Python addresses are not Linux native TIDs',
                interpretation='Wait-boundary observations are not evidence of CPU spent waiting, a busy loop, or a safe executor fix.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', type=Path)
    parser.add_argument('telemetry', type=Path)
    parser.add_argument('--hz', type=float, default=100)
    parser.add_argument('--executor-sha')
    args = parser.parse_args()
    result = analyze(json.loads(args.profile.read_bytes()),
                     [json.loads(line) for line in args.telemetry.read_text().splitlines() if line],
                     args.hz, args.executor_sha)
    result['input_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in (args.profile, args.telemetry)}
    print(json.dumps(result, indent=2))
