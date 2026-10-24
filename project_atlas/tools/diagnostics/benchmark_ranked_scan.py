"""PC-only /proc scanner microbenchmark; no perf, ROS, SSH, or production work."""
import inspect
import json
import platform
import time
import ranked_cpu_once as R

if platform.machine()!='x86_64':raise SystemExit('PC only')
source=inspect.getsource(R.snapshot)
change='            if cgroup not in GROUPS or root.stat().st_uid != os.getuid():\n                continue\n'
assert source.count(change)==1
namespace=dict(R.__dict__)
exec(source.replace(change,''),namespace)
baseline=namespace['snapshot']
for pair in range(4):
    for candidate in (bool(pair%2),not bool(pair%2)):
        begin=time.process_time()
        fn=R.snapshot if candidate else baseline
        counts=[]
        for _ in range(20):
            rows=fn(lambda pid:{})
            counts.append(len(rows))
        print(json.dumps(dict(pair=pair,candidate=candidate,cpu_s=time.process_time()-begin,
                              scans=20,min_rows=min(counts),max_rows=max(counts))))
