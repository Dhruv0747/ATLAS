"""Synthetic offline profile of actual extracted methods, no ROS/live access."""
import cProfile
import argparse
import io
import json
import pstats
import statistics
import time
from pathlib import Path
from types import SimpleNamespace
from test_status_web_snapshot_cost import SOURCE, baseline, load, state


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path)
    parser.add_argument('--candidate',type=Path,default=SOURCE)
    args=parser.parse_args()
    clock=SimpleNamespace(monotonic=lambda:100.,time=lambda:200.)
    history={str(i):[100-(127-n)*.02 for n in range(128)] for i in range(100)}
    report={}
    before=args.baseline.read_text(encoding='utf-8') if args.baseline else baseline()
    for label,source in [('baseline',before),('candidate',args.candidate.read_text(encoding='utf-8'))]:
        methods=load(source,clock,{'data':{},'updated_at':0})
        obj=state(history)
        values=[]
        for _ in range(5):
            start=time.process_time()
            for i in range(2000): methods['snapshot'](obj)
            values.append((time.process_time()-start)/2000*1e3)
        callback=[]
        for _ in range(5):
            start=time.process_time()
            for i in range(100000): methods['_set'](obj,'0',i)
            callback.append((time.process_time()-start)/100000*1e6)
        profiler=cProfile.Profile();profiler.enable()
        for i in range(1000):methods['snapshot'](obj)
        profiler.disable();out=io.StringIO()
        pstats.Stats(profiler,stream=out).sort_stats('cumulative').print_stats(8)
        report[label]={'snapshot_median_cpu_ms':statistics.median(values),
                       'callback_median_cpu_us':statistics.median(callback),
                       'profile':out.getvalue()}
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
