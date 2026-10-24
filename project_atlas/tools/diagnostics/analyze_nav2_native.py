"""Offline native call-path accounting; inclusive counts are NOT additive CPU."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re


def stacks(text):
    blocks = re.split(r'\n\s*\n', text.strip())
    counts = Counter()
    tids = Counter()
    periods = Counter()
    for block in blocks:
        lines = block.splitlines()
        header = re.fullmatch(r'(\S+)\s+(\d+)\s+(\d+)\s+cpu-clock:u:\s*', lines[0])
        if not header:
            raise ValueError('Unexpected perf script header')
        _, tid, period = header.groups()
        if int(period) <= 0 or len(lines) < 2:
            raise ValueError('Empty/invalid sample')
        tids[tid] += 1
        periods[tid] += int(period)
        # Count a path at most once per sample, even with repeated/inlined frames.
        for key, needles in {
            'wait_set_attach_detach': ('WaitSetImpl::attach_condition', 'WaitSetImpl::detach_condition'),
            'executor_wait_for_work': ('Executor::wait_for_work',),
            'subscription_dispatch': ('get_subscription_by_handle', 'Executor::execute_subscription', 'rcl_take+'),
            'bond_publish': ('bond::Bond::publishStatus',),
        }.items():
            if any(needle in '\n'.join(lines[1:]) for needle in needles):
                counts[key] += 1
    return dict(samples=sum(tids.values()), samples_by_tid=dict(tids),
                sampled_user_cpu_ns_by_tid=dict(periods), inclusive_paths=dict(counts),
                warning='Small selected-thread sample; inclusive paths overlap. Not whole-system CPU or proof of a defect.')


def thread_cpu(rows, hz):
    rows = [r for r in rows if 'threads' in r]
    if hz <= 0 or len(rows) < 2:
        raise ValueError('Need positive HZ and two snapshots')
    elapsed = 0
    totals = Counter()
    for a,b in zip(rows,rows[1:]):
        dt=b['monotonic']-a['monotonic']
        if dt <= 0:
            raise ValueError('Invalid time')
        elapsed += dt
        for tid,q in b['threads'].items():
            p=a['threads'].get(tid)
            if p is None or p['birth'] != q['birth'] or p['tgid'] != q['tgid']:
                continue
            delta=q['ticks']-p['ticks']
            if delta < 0:
                raise ValueError('Regressing thread counter')
            totals[q['tgid']] += delta
    return dict(elapsed_s=elapsed, one_core_percent_by_tgid={
        pid:100*ticks/hz/elapsed for pid,ticks in totals.most_common()})


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('perf_script',type=Path)
    parser.add_argument('telemetry',type=Path)
    parser.add_argument('--hz',type=int,required=True)
    args=parser.parse_args()
    print(json.dumps(dict(native=stacks(args.perf_script.read_text()),
        cpu=thread_cpu([json.loads(line) for line in args.telemetry.read_text().splitlines()],args.hz)),indent=2))
