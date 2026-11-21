"""Isolated synthetic benchmark; NOT a live safety validator or activation tool.
Run on Jetson only under separately approved external safety supervision.
No ROS, sockets, service operations or production paths. Maximum12s workload.
"""
import argparse
import json
import resource
import tempfile
import time
from pathlib import Path
from existing_safety_snapshot import Producer, Consumer


def observations(now):
    return {'policy': {'stop_latched': True, 'manual_only': True,
                       'commission_armed': False, 'source': 'STOPPED'},
            'command': [0.0]*6,
            'encoders': {'packet_fresh': True, 'link_state': 'LIVE',
                         'packet_age_s': 0.01, 'encoder_interval_delta_m': [0.0]*4}}


def phase(enabled, duration, path):
    producer=Producer(path,'synthetic-only')
    consumer=Consumer(path,'synthetic-only')
    start=time.monotonic(); cpu=time.process_time(); count=0
    deadline=start+duration
    while time.monotonic()<deadline:
        now=time.monotonic(); values=observations(now)
        if enabled:
            # Same callback-shaped work; preload simulates prior received topics.
            producer.values={k:[v,now] for k,v in values.items()}
            producer.receive('command',values['command'],now)
            consumer.check(time.monotonic())
        count+=1
        time.sleep(min(.1,max(0,deadline-time.monotonic())))
    return {'enabled':enabled,'wall_s':time.monotonic()-start,
            'process_cpu_s':time.process_time()-cpu,'iterations':count,
            'maxrss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase-seconds',type=float,default=2)
    args=parser.parse_args()
    if not .1<=args.phase_seconds<=2:raise ValueError('phase duration outside bounds')
    with tempfile.TemporaryDirectory(prefix='atlas-synthetic-snapshot-') as directory:
        rows=[phase(enabled,args.phase_seconds,Path(directory)/'snapshot.json')
              for enabled in (False,True,True,False,False,True)]
    print(json.dumps({'synthetic_only':True,'rows':rows,
        'rss_note':'process high-water mark, not incremental allocation; ROS excluded'},indent=2))

if __name__=='__main__':main()
