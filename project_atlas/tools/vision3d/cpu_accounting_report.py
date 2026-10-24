"""Offline all-PID /proc accounting. Never connects to or controls ATLAS."""
import argparse
import json


def analyze(capture):
    samples = capture['samples']
    hz, cpus = capture['hz'], capture['cpus']
    if len(samples) < 2 or hz <= 0 or cpus <= 0:
        raise ValueError('Need two samples and positive HZ/CPU count')
    sums = [0] * 8
    processes = {}
    intervals = []
    unmatched = 0
    for a, b in zip(samples, samples[1:]):
        elapsed = b['monotonic'] - a['monotonic']
        delta = [y-x for x, y in zip(a['cpu'][:8], b['cpu'][:8])]
        if len(delta) != 8 or elapsed <= 0 or min(delta) < 0 or sum(delta) <= 0:
            raise ValueError('Invalid clock or CPU counter interval')
        sums = [x+y for x, y in zip(sums, delta)]
        intervals.append(100*(sum(delta)-delta[3]-delta[4])/sum(delta))
        for pid, q in b['processes'].items():
            p = a['processes'].get(pid)
            if p is None or p['birth'] != q['birth']:
                unmatched += 1
                continue
            ticks = q['user'] + q['system'] - p['user'] - p['system']
            if ticks < 0:
                raise ValueError('Regressing process counter')
            # Do not assign earlier CPU to a process's final cgroup after a move.
            key = (pid, q['birth'], q['cgroup'])
            row = processes.setdefault(key, dict(pid=pid, birth=q['birth'],
                name=q['name'], cgroup=q['cgroup'], kernel=q['kernel'], ticks=0))
            row['ticks'] += ticks
    total = sum(sums)
    elapsed = samples[-1]['monotonic'] - samples[0]['monotonic']
    rows = sorted(processes.values(), key=lambda r: r['ticks'], reverse=True)
    for row in rows:
        row['one_core_percent'] = 100*row['ticks']/hz/elapsed
        row['aggregate_tick_percent'] = 100*row['ticks']/total
    accounted = sum(r['ticks'] for r in rows)
    busy = total-sums[3]-sums[4]
    groups = {}
    for row in rows:
        group = groups.setdefault(row['cgroup'], dict(cgroup=row['cgroup'],
            ticks=0, members=[]))
        group['ticks'] += row['ticks']
        group['members'].append(dict(pid=row['pid'], birth=row['birth'],
                                    name=row['name'], ticks=row['ticks']))
    for group in groups.values():
        group['one_core_percent'] = 100*group['ticks']/hz/elapsed
        group['aggregate_tick_percent'] = 100*group['ticks']/total
    return dict(elapsed_s=elapsed, cpu_count=cpus,
        cpu_percent=100*busy/total, interval_cpu_range=[min(intervals), max(intervals)],
        user_percent=100*(sums[0]+sums[1])/total,
        system_percent=100*sums[2]/total, irq_percent=100*sums[5]/total,
        softirq_percent=100*sums[6]/total,
        accounted_pid_percent=100*accounted/total,
        unassigned_percent=100*(busy-accounted)/total,
        kernel_thread_percent=100*sum(r['ticks'] for r in rows if r['kernel'])/total,
        top10_percent=100*sum(r['ticks'] for r in rows[:10])/total,
        new_or_reused_pid_intervals=unmatched,
        observer_capacity_percent=100*capture.get('observer_cpu_s', 0)/elapsed/cpus,
        processes=rows,
        cgroups=sorted(groups.values(), key=lambda r: r['ticks'], reverse=True),
        limitations=['Intervals are not atomic; exited processes can be missed.',
                    'Cgroup changes are attributed to the interval end group.',
                    'Cgroups combine child processes, not identical executable names.',
                    'IRQ work and PID work must not be added blindly.',
                    'CPU utilization and message age do not measure safety deadlines.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture')
    args = parser.parse_args()
    with open(args.capture, encoding='utf-8') as stream:
        print(json.dumps(analyze(json.load(stream)), indent=2))
