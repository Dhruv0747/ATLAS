"""Offline ranked capture accounting. PID totals and TID subsets stay separate."""
import argparse
from collections import Counter
import json
from pathlib import Path
import statistics


def summarize(rows, hz=100):
    samples=[r for r in rows if 'threads' in r]
    if len(samples)<2 or hz<=0:raise ValueError('Missing snapshots/HZ')
    elapsed=samples[-1]['monotonic']-samples[0]['monotonic']
    if elapsed<=0:raise ValueError('Invalid interval')
    totals={kind:Counter() for kind in ('process_total','thread')}
    meta={}
    for a,b in zip(samples,samples[1:]):
        if b['monotonic']<=a['monotonic']:raise ValueError('Nonmonotonic snapshots')
        for key,q in b['threads'].items():
            p=a['threads'].get(key)
            if p is None or any(p.get(k)!=q.get(k) for k in ('birth','tgid','cgroup','kind','process_birth')):continue
            delta=q['ticks']-p['ticks']
            if delta<0:raise ValueError('Counter regressed')
            kind=q['kind']
            if kind not in totals:raise ValueError('Invalid row kind')
            identity=(key,q['birth'],q['tgid'],q['cgroup'],q.get('process_birth'))
            totals[kind][identity]+=delta;meta[identity]=q
    result={'elapsed_s':elapsed}
    for kind,counts in totals.items():
        result[kind]=[dict(key=k[0],name=meta[k]['name'],cgroup=meta[k]['cgroup'],
                          tgid=meta[k]['tgid'],cpu_one_core_pct=100*v/hz/elapsed)
                      for k,v in counts.most_common()]
    groups=Counter()
    for r in result['process_total']:groups[r['cgroup']]+=r['cpu_one_core_pct']
    result['groups_one_core_pct']=groups.most_common()
    result['phases']={phase:dict(n=len(values),mean=statistics.mean(values),peak=max(values))
                      for phase in ('baseline','profile','postflight')
                      if (values:=[r['cpu'] for r in samples if r['phase']==phase])}
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('telemetry',type=Path)
    args=parser.parse_args()
    result=summarize([json.loads(x) for x in args.telemetry.read_text().splitlines()])
    for key in ('process_total','thread','groups_one_core_pct'):result[key]=result[key][:20]
    print(json.dumps(result,indent=2))
