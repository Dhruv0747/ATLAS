#!/usr/bin/env python3
"""Finite read-only Linux resource window; no ROS, service or network changes."""
import argparse
import json
import os
from pathlib import Path
import time
import urllib.request


def snapshot():
    cpu = [int(v) for v in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
    mem = {line.split(':')[0]: int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
    processes = {}
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            text = path.read_text()
            end = text.rfind(')')
            fields = text[end+2:].split()
            processes[path.parent.name] = dict(name=text[text.index('(')+1:end],
                start=fields[19], ticks=int(fields[11])+int(fields[12]),
                rss_bytes=int(fields[21])*os.sysconf('SC_PAGE_SIZE'))
        except (OSError, ValueError, IndexError):
            continue
    return dict(cpu=cpu, mem=mem, processes=processes, monotonic=time.monotonic())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=20)
    args = parser.parse_args()
    if args.out.exists() or not 5 <= args.seconds <= 45:
        parser.error('new output file and 5..45 seconds required')
    before = snapshot()
    time.sleep(args.seconds)
    after = snapshot()
    elapsed = after['monotonic']-before['monotonic']
    delta = [b-a for a,b in zip(before['cpu'],after['cpu'])]
    total = sum(delta)
    hz = os.sysconf('SC_CLK_TCK')
    cores = os.cpu_count()
    rows=[]
    for pid, now in after['processes'].items():
        old=before['processes'].get(pid)
        if old and old['start']==now['start']:
            core_pct=100*(now['ticks']-old['ticks'])/hz/elapsed
            rows.append(dict(pid=int(pid),name=now['name'],cpu_one_core_percent=core_pct,
                             cpu_machine_percent=core_pct/cores,rss_mib=now['rss_bytes']/2**20))
    result=dict(duration_s=elapsed,logical_cpus=cores,
                cpu_busy_percent=100*(total-delta[3]-delta[4])/total,
                cpu_iowait_percent=100*delta[4]/total,
                ram_used_mib=(after['mem']['MemTotal']-after['mem']['MemAvailable'])/1024,
                ram_definition='MemTotal minus MemAvailable; not process RSS sum',
                top_cpu=sorted(rows,key=lambda r:r['cpu_one_core_percent'],reverse=True)[:12],
                top_rss=sorted(rows,key=lambda r:r['rss_mib'],reverse=True)[:12],
                probe=next((r for r in rows if r['pid']==os.getpid()),None), http=[])
    # HTTP measurements are AFTER the settled CPU window, not hidden load in it.
    for route in ('/','/api/status','/api/lidar-view'):
        started=time.monotonic()
        try:
            with urllib.request.urlopen('http://127.0.0.1:8088'+route,timeout=4) as response:
                body=response.read()
                result['http'].append(dict(route=route,status=response.status,bytes=len(body),seconds=time.monotonic()-started))
        except Exception as exc:
            result['http'].append(dict(route=route,error=str(exc),seconds=time.monotonic()-started))
    with args.out.open('x') as stream:
        json.dump(result,stream,indent=2)
    args.out.chmod(0o600)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
