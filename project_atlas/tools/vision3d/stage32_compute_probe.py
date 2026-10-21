"""Stage32 camera-free compute probe: per-frame cost of (a) IR raw serving path, (b) depth->XYZ backprojection
with/without distortion, (c) PointCloud2 packing. Synthetic fixtures; no ROS, no USB, no network."""
import json, struct, sys, time, resource
from types import SimpleNamespace as N
sys.path.insert(0, sys.argv[1] + '/scripts')
import atlas_vision3d_geometry as G
import atlas_vision3d_web as W

def t(fn, n):
    c0, w0 = time.process_time(), time.perf_counter()
    for _ in range(n): fn()
    return {'cpu_ms': round((time.process_time() - c0) / n * 1000, 2), 'wall_ms': round((time.perf_counter() - w0) / n * 1000, 2)}

h = N(frame_id='astra_depth_optical_frame', stamp=N(sec=1, nanosec=0))
depth = N(width=160, height=120, encoding='16UC1', step=320, is_bigendian=False, header=h,
          data=struct.pack('<' + 'H' * 19200, *[0 if (x * y) % 17 == 0 else 900 + x + y for y in range(120) for x in range(160)]))
cal0 = {'width': 160, 'height': 120, 'frame_id': 'astra_depth_optical_frame', 'k': [140., 0, 79.5, 0, 140., 59.5, 0, 0, 1], 'd': [0, 0, 0, 0, 0]}
cal1 = dict(cal0, d=[0.05, -0.1, 0.001, 0.001, 0.02])
out = {}
out['backproject_no_distortion'] = t(lambda: G.backproject(depth, cal0), 20)
G._RAYS.clear(); out['backproject_plumb_bob_first_frame'] = t(lambda: G.backproject(depth, cal1), 1)
out['backproject_plumb_bob_steady'] = t(lambda: G.backproject(depth, cal1), 20)
pts, st = G.backproject(depth, cal1); out['points'] = st
out['pc2_pack_6000'] = t(lambda: G.pointcloud2_fields(pts), 20)
now = [100.0]; s = W.VisionService({'topics': {}}, clock=lambda: now[0], wall=lambda: now[0])
ir = N(width=320, height=240, encoding='mono8', step=320, is_bigendian=False, data=bytes(range(256)) * 300, header=N(frame_id='astra_ir_optical_frame', stamp=N(sec=100, nanosec=0)))
def ir_cycle():
    now[0] += 0.2; ir.header.stamp.sec = int(now[0]); ir.header.stamp.nanosec = int((now[0] % 1) * 1e9); s.ingest('ir', ir); s.raw('ir')
out['ir_ingest_plus_raw'] = t(ir_cycle, 50)
out['max_rss_mb'] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
print(json.dumps(out))
