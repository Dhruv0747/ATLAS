"""Offline-only next candidate; reuse the executor-local entity accumulator.

Never modifies a live file. Requires exact original captured source and builds
on the deployed cancellation/count fixes. No cached entities or QoS changes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import benchmark_executor_counts as B
import benchmark_executor_loaded as L

DEPLOYED_IMPL_SHA='543e41125a6095ba5a69f114deaa2dc4cf54c4df2029f78fdb80c99ecf81b5c1'
DEPLOYED_ADAPTER_SHA='2b6ceeae09ec63cafd8a93084ba086c0e5145661f56a245966de4eed389f11ab'

def package(raw, adapter, output):
    """Prepare two-file candidate only. Existing directory/hash mismatch aborts."""
    baseline=B.cancellation_candidate(raw,True).encode()
    if hashlib.sha256(baseline).hexdigest()!=DEPLOYED_IMPL_SHA:
        raise ValueError('deployed implementation mismatch')
    if hashlib.sha256(adapter).hexdigest()!=DEPLOYED_ADAPTER_SHA:
        raise ValueError('deployed adapter mismatch')
    impl=candidate(raw).encode()
    sha=hashlib.sha256(impl).hexdigest()
    if adapter.count(DEPLOYED_IMPL_SHA.encode())!=1:
        raise ValueError('ambiguous adapter hash')
    patched=adapter.replace(DEPLOYED_IMPL_SHA.encode(),sha.encode())
    compile(patched,'<offline-adapter>','exec')
    output.mkdir(exist_ok=False)
    payload={'atlas_dashboard_executor.py':patched,'atlas_dashboard_executor_impl.py':impl}
    for name,content in payload.items(): (output/name).write_bytes(content)
    (output/'adapter.original').write_bytes(adapter)
    (output/'implementation.original').write_bytes(baseline)
    manifest={'installed':False,'files':{k:hashlib.sha256(v).hexdigest() for k,v in payload.items()},
              'baseline':{'adapter':DEPLOYED_ADAPTER_SHA,'implementation':DEPLOYED_IMPL_SHA},
              'production_approval_required':True}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest

def accumulate(left, right):
    # Evaluate every sum before assigning, preserving failure atomicity.
    (left.num_subscriptions, left.num_guard_conditions, left.num_timers,
     left.num_clients, left.num_services, left.num_events) = (
        left.num_subscriptions + right.num_subscriptions,
        left.num_guard_conditions + right.num_guard_conditions,
        left.num_timers + right.num_timers,
        left.num_clients + right.num_clients,
        left.num_services + right.num_services,
        left.num_events + right.num_events)
    return left

def candidate(raw):
    source = B.cancellation_candidate(raw, True)
    # This count object is freshly allocated inside each wait-set construction,
    # never exposed to callbacks. Do not mutate objects returned by waitables.
    new = ('                        added_count = waitable.get_num_entities()\n'
           '                        (' + ', '.join('entity_count.'+f for f in B.FIELDS) + ') = (\n' +
           ''.join('                            entity_count.'+f+' + added_count.'+f+',\n' for f in B.FIELDS) +
           '                        )')
    if source.count(B.NEW) != 1:
        raise ValueError('ambiguous deployed count block')
    result = source.replace(B.NEW, new)
    compile(result, '<offline-accumulator>', 'exec')
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--pairs',type=int,default=6)
    p.add_argument('--rounds',type=int,default=300)
    a=p.parse_args()
    if os.environ.get('ROS_LOCALHOST_ONLY')!='1' or os.environ.get('ROS_DOMAIN_ID')!='213':
        raise RuntimeError('PC localhost domain213 required')
    if not 2<=a.pairs<=10 or not 10<=a.rounds<=2000:
        raise ValueError('bounded workload required')
    raw=a.source.read_bytes()
    sources={'deployed':B.cancellation_candidate(raw,True),'accumulator':candidate(raw)}
    modules={k:B.load_executor(v,'offline_'+k) for k,v in sources.items()}
    rows=[]
    for pair in range(a.pairs):
        for name in (['deployed','accumulator'] if pair%2==0 else ['accumulator','deployed']):
            row=L.run_case(modules[name],pair,name,a.rounds)
            rows.append(row)
            print(json.dumps(row),flush=True)
    savings=[]
    for pair in range(a.pairs):
        r={x['variant']:x for x in rows if x['pair']==pair}
        savings.append(100*(1-r['accumulator']['cpu_s']/r['deployed']['cpu_s']))
    result={'rows':rows,'paired_cpu_savings_percent':savings,
            'median_cpu_savings_percent':statistics.median(savings),
            'all_delivered':all(x['sent']==x['received'] and not x['errors'] for x in rows)}
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'}))

if __name__=='__main__': main()
