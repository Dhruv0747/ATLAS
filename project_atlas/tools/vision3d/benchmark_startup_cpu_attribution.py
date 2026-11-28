"""PC-only reproducible collector microbenchmark; never run as live admission."""
import argparse
import importlib.util
import json
from pathlib import Path
import resource
import statistics
import tempfile
import time
import startup_cpu_attribution as new

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--old',required=True);args=p.parse_args()
    spec=importlib.util.spec_from_file_location('old_collector',args.old);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    records={'new':[],'old':[]};counts={}
    group=Path('/sys/fs/cgroup');groups=[('root',group,2)] if (group/'cpu.stat').exists() else []
    with tempfile.TemporaryDirectory() as d:
        for i in range(30):
            for label in (('new','old') if i%2==0 else ('old','new')):
                before=time.monotonic();cpu=time.process_time()
                s=new.snapshot(groups=groups) if label=='new' else old.snapshot()
                # Both include identical durable JSON evidence-write work.
                new.persist(Path(d),i*2+(label=='old'),s)
                records[label].append({'wall_ms':1000*(time.monotonic()-before),'cpu_ms':1000*(time.process_time()-cpu)})
                counts[label]={'pids':len(s['processes']),'groups':len(s['groups'])}
    out={'platform':'PC WSL Ubuntu22.04; NOT Jetson','iterations_each':30,'counts':counts,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    for label,rows in records.items():
        out[label]={key:{'mean':statistics.mean(r[key] for r in rows),'max':max(r[key] for r in rows)} for key in ('wall_ms','cpu_ms')}
    print(json.dumps(out,indent=2))
