"""Offline summarize retained deployment samples; never infer missing process attribution."""
import json
from pathlib import Path

def summarize(resources, journals):
    samples=[{'monotonic':r['monotonic'],'cpu_pct':r['cpu_pct'],'over_75':r['cpu_pct']>75} for r in resources]
    events=[]
    for r in journals:
        message=r.get('MESSAGE','')
        if 'sensor recovery' in message or ('atlas-sensor-recovery.service:' in message):
            events.append({'monotonic':int(r['__MONOTONIC_TIMESTAMP'])/1e6,'message':message})
    return {'samples':samples,'events':events,'process_attribution':'UNKNOWN: no synchronized per-process CPU deltas',
            'duration':'UNKNOWN: isolated samples do not establish transient or sustained load',
            'retry_recommendation':'NO-GO: cause not established'}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args()
    resources=json.loads((a.directory/'resources.json').read_text())
    journals=[json.loads(s) for s in (a.directory/'journal-window.jsonl').read_text(encoding='utf-8-sig').splitlines()]
    print(json.dumps(summarize(resources,journals),indent=2))
