"""Synthetic PC benchmark, no ROS/hardware/network; stdout JSON only."""
import cProfile,hashlib,importlib.util,json,statistics,subprocess,sys,time,tracemalloc,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'project_atlas/tests'))
from test_vision3d_preview_cpu import frame
import atlas_vision3d_core as candidate
source=subprocess.check_output(['git','show','06ed75f:project_atlas/scripts/atlas_vision3d_core.py'],cwd=ROOT,text=True)
baseline=types.ModuleType('old_preview');exec(compile(source,'old_preview','exec'),baseline.__dict__)
m=frame();assert baseline.preview(m,'depth')==candidate.preview(m,'depth')
result={'fixture':'synthetic160x12016UC1 padded; no sensor data','python':sys.version,'iterations_per_batch':20,'batches':7}
for name,module in [('baseline',baseline),('candidate',candidate)]:
    module.preview(m,'depth');samples=[]
    for _ in range(7):
        start=time.process_time()
        for _ in range(20):module.preview(m,'depth')
        samples.append((time.process_time()-start)/20)
    p=cProfile.Profile();p.runcall(module.preview,m,'depth')
    calls={}
    for entry in p.getstats():
        if hasattr(entry.code,'co_name') and entry.code.co_name in ('image_layout','depth_at'):
            calls[entry.code.co_name]=entry.callcount
    tracemalloc.start();module.preview(m,'depth');_,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    result[name]={'cpu_seconds_per_frame':samples,'median':statistics.median(samples),'peak_traced_bytes':peak,'profile_calls':calls}
result['cpu_reduction_percent']=100*(1-result['candidate']['median']/result['baseline']['median'])
result['png_sha256']=hashlib.sha256(candidate.preview(m,'depth')[0]).hexdigest()
print(json.dumps(result,indent=2))
