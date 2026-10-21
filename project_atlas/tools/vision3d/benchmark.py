"""PC-only synthetic decoder benchmark; explicitly NOT Jetson camera overhead."""
import json
from pathlib import Path
import struct
import sys
import time
import tracemalloc
from types import SimpleNamespace as N
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import atlas_vision3d_core as C

if __name__=='__main__':
    m=N(width=640,height=480,step=1280,encoding='16UC1',is_bigendian=False,
        data=struct.pack('<H',1200)*640*480,header=N(frame_id='sim_optical_frame',stamp=N(sec=100,nanosec=0)))
    # Timing separately from tracemalloc, which substantially inflates Python-loop time.
    start=time.process_time();sizes=[]
    for _ in range(10):sizes.append(len(C.preview(m,'depth')[0]))
    cpu=(time.process_time()-start)/10
    tracemalloc.start();C.preview(m,'depth');_,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    print(json.dumps({'synthetic':True,'host':sys.platform,'source_pixels':640*480,'depth_preview_cpu_seconds_per_frame':cpu,
                      'png_bytes':max(sizes),'python_conversion_peak_bytes':peak,'jetson_stream_overhead':'NOT MEASURED',
                      'gpu_usage':'No GPU code in converter; browser renders offboard','recording_bytes_written':0},indent=2))
