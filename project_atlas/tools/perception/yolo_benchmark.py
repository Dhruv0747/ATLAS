#!/usr/bin/env python3
"""ATLAS master-plan step 8: benchmark the EXISTING TensorRT YOLO path (read-only, no motion, no ROS). 2026-11-23.

Plan text: "Benchmark the existing TensorRT YOLO path, optional and resource-capped. Measure FPS, latency,
CPU/GPU/RAM and temperature under Nav2 load." Nothing is rebuilt: the engine is
scripts/yolov8n_fp16.engine via scripts/trt_yolo_detector.TensorRTYOLO (the same class ai_annotator_node uses).

With ATLAS PARKED and the normal stack running, the tool:
  1. samples the system for 5 s WITHOUT YOLO (baseline CPU, RAM, temperature, GPU load);
  2. runs YOLO on live IMX708 frames (/camera.jpg, refreshed every 0.5 s) at most 10 inferences/s for 20 s;
  3. STOPS AT ONCE if CPU >= 75 % for 3 samples in a row, RAM >= 80 % or any temperature >= 70 C (ATLAS limits).
Verdicts (evaluate):
  PASS          p95 latency <= 100 ms, >= 9 inferences/s, and every limit held under the running stack
  NOT ADVISED   it runs, but it is too slow or pushes ATLAS over a limit: YOLO stays off by default (Eco) and
                on demand only; this completes the evaluation honestly
  FAIL          not parked, engine did not load, or no inference ran
Writes ~/.local/state/project_atlas/yolo_bench_<time>.json and records step 8 on the master plan.
"""
import json
import math
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path('/home/jetson/project_atlas')
HERE = Path(__file__).resolve()
for p in (ROOT / 'scripts', HERE.parents[2] / 'scripts'):
    sys.path.insert(0, str(p))

ENGINE = ROOT / 'scripts/yolov8n_fp16.engine'
DASH = 'http://127.0.0.1:8088'
LIMITS = {'cpu_pct': 75.0, 'ram_pct': 80.0, 'temp_c': 70.0}
TARGET = {'p95_ms': 100.0, 'min_hz': 9.0}
RUN_S, BASE_S, MAX_HZ, CPU_STRIKES = 20.0, 5.0, 10.0, 3
NAV_SERVICES = ('atlas-localization', 'atlas-ekf', 'atlas-lidar', 'atlas-icp-odometry')
# 2026-11-23: Nav2 runs inside atlas-localization.service (atlas-nav2.service is inactive), so the Nav2 servers are
# checked as processes
NAV_PROCESSES = ('bt_navigator', 'controller_server', 'planner_server')
GPU_LOAD_FILES = ('/sys/devices/platform/gpu.0/load', '/sys/devices/gpu.0/load',
                  '/sys/devices/platform/17000000.gpu/load', '/sys/devices/platform/bus@0/17000000.gpu/load')


def percentile(values, q):
    v = sorted(values)
    if not v:
        return None
    return v[min(len(v) - 1, max(0, int(math.ceil(q * len(v))) - 1))]


def evaluate(parked, engine_ok, latencies_ms, run_s, base, load, stop_reason, nav_missing):
    """Pure; unit-tested. base / load: lists of {'cpu_pct','ram_pct','temp_c','gpu_pct'} samples."""
    def peak(samples, k):
        vals = [s[k] for s in samples if s.get(k) is not None]
        return max(vals) if vals else None

    def mean(samples, k):
        vals = [s[k] for s in samples if s.get(k) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None
    n = len(latencies_ms)
    p50, p95 = percentile(latencies_ms, 0.5), percentile(latencies_ms, 0.95)
    hz = n / run_s if run_s > 0 else 0.0
    c = {'parked': bool(parked), 'engine_loaded': bool(engine_ok), 'inference_ran': n >= 10,
         'latency_p95_ok': p95 is not None and p95 <= TARGET['p95_ms'],
         'rate_ok': hz >= TARGET['min_hz'],
         'cpu_limit_held': stop_reason != 'CPU',            # 3 samples >= 75 % in a row = the hard stop
         'ram_limit_held': stop_reason != 'RAM' and (peak(load, 'ram_pct') or 0) < LIMITS['ram_pct'],
         'temp_limit_held': stop_reason != 'TEMP' and (peak(load, 'temp_c') or 0) < LIMITS['temp_c'],
         'under_nav_stack': not nav_missing}
    if not (c['parked'] and c['engine_loaded'] and c['inference_ran']):
        verdict = 'FAIL'
    elif all(c.values()):
        verdict = 'PASS'
    else:
        verdict = 'NOT ADVISED'
    blockers = [k for k in ('latency_p95_ok', 'rate_ok', 'cpu_limit_held', 'ram_limit_held', 'temp_limit_held',
                            'under_nav_stack') if not c[k]]
    measured = {'inferences': n, 'run_s': round(run_s, 1), 'rate_hz': round(hz, 2),
                'latency_ms_p50': None if p50 is None else round(p50, 1),
                'latency_ms_p95': None if p95 is None else round(p95, 1),
                'cpu_pct_base': mean(base, 'cpu_pct'), 'cpu_pct_yolo': mean(load, 'cpu_pct'),
                'cpu_pct_peak': peak(load, 'cpu_pct'), 'ram_pct_peak': peak(load, 'ram_pct'),
                'temp_c_base': peak(base, 'temp_c'), 'temp_c_peak': peak(load, 'temp_c'),
                'gpu_pct_base': mean(base, 'gpu_pct'), 'gpu_pct_yolo': mean(load, 'gpu_pct'),
                'stopped_early': stop_reason, 'nav_services_missing': list(nav_missing)}
    detail = {
        'PASS': 'YOLO %.1f inferences/s, p95 %.0f ms; CPU %s -> %s %%, peak %s C: within limits under the running '
                'stack' % (hz, p95 or 0, measured['cpu_pct_base'], measured['cpu_pct_yolo'], measured['temp_c_peak']),
        'NOT ADVISED': 'YOLO runs (%.1f/s, p95 %s ms) but %s; keep it off by default (Eco) and on demand only'
                       % (hz, measured['latency_ms_p95'], ', '.join(blockers)),
        'FAIL': 'benchmark did not run: ' + ', '.join(k for k in ('parked', 'engine_loaded', 'inference_ran')
                                                          if not c[k]),
    }[verdict]
    return {'verdict': verdict, 'checks': c, 'blockers': blockers, 'measured': measured, 'detail': detail,
            'failed': [k for k in ('parked', 'engine_loaded', 'inference_ran') if not c[k]] if verdict == 'FAIL'
            else blockers}


# ---- live system sampling (shared with step 9) -------------------------------------------------------------------
class SystemSampler:
    def __init__(self):
        self.prev = self._cpu_times()

    @staticmethod
    def _cpu_times():
        try:
            f = [float(x) for x in Path('/proc/stat').read_text().split('\n')[0].split()[1:]]
            return sum(f), f[3] + (f[4] if len(f) > 4 else 0.0)
        except (OSError, ValueError, IndexError):
            return None

    def sample(self):
        s = {'cpu_pct': None, 'ram_pct': None, 'temp_c': None, 'gpu_pct': None}
        cur = self._cpu_times()
        if cur and self.prev and cur[0] > self.prev[0]:
            s['cpu_pct'] = round(100.0 * (1 - (cur[1] - self.prev[1]) / (cur[0] - self.prev[0])), 1)
        self.prev = cur
        try:
            mi = {l.split(':')[0]: float(l.split()[1]) for l in Path('/proc/meminfo').read_text().splitlines()[:5]}
            s['ram_pct'] = round(100.0 * (1 - mi['MemAvailable'] / mi['MemTotal']), 1)
        except (OSError, ValueError, KeyError, IndexError):
            pass
        temps = []
        for z in Path('/sys/class/thermal').glob('thermal_zone*/temp'):
            try:
                t = float(z.read_text()) / 1000.0
                if 0 < t < 120:
                    temps.append(t)
            except Exception:              # some sysfs zones fail to read on this Jetson
                pass
        s['temp_c'] = round(max(temps), 1) if temps else None
        for g in GPU_LOAD_FILES:
            try:
                s['gpu_pct'] = round(float(Path(g).read_text()) / 10.0, 1)
                break
            except Exception:
                continue
        return s


def over_limit(s, cpu_strikes):
    """(stop_reason or None, new cpu strike count)."""
    strikes = cpu_strikes + 1 if (s.get('cpu_pct') or 0) >= LIMITS['cpu_pct'] else 0
    if (s.get('ram_pct') or 0) >= LIMITS['ram_pct']:
        return 'RAM', strikes
    if (s.get('temp_c') or 0) >= LIMITS['temp_c']:
        return 'TEMP', strikes
    if strikes >= CPU_STRIKES:
        return 'CPU', strikes
    return None, strikes


def dash_json(path, timeout=2):
    with urllib.request.urlopen(DASH + path, timeout=timeout) as r:
        return json.load(r)


def wheel_still():
    try:
        v = (dash_json('/api/status').get('ros') or {}).get('odom', {}).get('value')
        v = json.loads(v) if isinstance(v, str) else v
        return abs(float((v or {}).get('vx') or 0)) <= 0.02 and abs(float((v or {}).get('wz') or 0)) <= 0.05
    except Exception:
        return False


def camera_rgb():
    import cv2
    import numpy as np
    try:
        with urllib.request.urlopen(DASH + '/camera.jpg', timeout=2) as r:
            img = cv2.imdecode(np.frombuffer(r.read(), np.uint8), cv2.IMREAD_COLOR)
        return None if img is None else cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    except Exception:
        return None


def nav_missing():
    import subprocess
    out = []
    for unit in NAV_SERVICES:
        if subprocess.run(['systemctl', '--user', 'is-active', '--quiet', unit + '.service']).returncode != 0:
            out.append(unit)
    for proc in NAV_PROCESSES:
        if subprocess.run(['pgrep', '-f', proc], stdout=subprocess.DEVNULL).returncode != 0:
            out.append(proc)
    return out


def main():
    print('Step 8: TensorRT YOLO benchmark. ATLAS does not move; keep it parked (~30 s).', flush=True)
    parked, missing = wheel_still(), nav_missing()
    sampler, base, load, lat = SystemSampler(), [], [], []
    engine_ok, stop, run_s = False, None, 0.0
    if parked:
        t_end = time.time() + BASE_S
        while time.time() < t_end:
            time.sleep(1.0)
            base.append(sampler.sample())
        print('baseline (no YOLO): %s' % base[-1], flush=True)
        det = None
        try:
            from trt_yolo_detector import TensorRTYOLO
            det = TensorRTYOLO(str(ENGINE))
            engine_ok = True
        except Exception as exc:
            print(f'engine did not load: {exc}', flush=True)
        rgb = camera_rgb()
        if engine_ok and rgb is None:
            import numpy as np
            rgb = np.full((720, 1280, 3), 114, np.uint8)
            print('no camera frame: benchmarking on a grey frame', flush=True)
        if engine_ok:
            for _ in range(5):
                det.infer(rgb)                       # warm-up, not timed
            t0 = time.time(); last_s = t0; last_frame = t0; strikes = 0
            while time.time() - t0 < RUN_S:
                loop_start = time.time()
                t = time.perf_counter()
                det.infer(rgb)
                lat.append((time.perf_counter() - t) * 1000.0)
                now = time.time()
                if now - last_frame >= 0.5:
                    fresh = camera_rgb()             # a new live frame twice a second (kept if none)
                    if fresh is not None:
                        rgb = fresh
                    last_frame = now
                if now - last_s >= 1.0:
                    s = sampler.sample(); load.append(s); last_s = now
                    stop, strikes = over_limit(s, strikes)
                    print('t=%4.1fs n=%d last %.0f ms cpu %s%% ram %s%% temp %s C gpu %s%%' % (
                        now - t0, len(lat), lat[-1], s['cpu_pct'], s['ram_pct'], s['temp_c'], s['gpu_pct']),
                        flush=True)
                    if stop:
                        print(f'STOP: {stop} limit reached, YOLO stopped', flush=True)
                        break
                pause = 1.0 / MAX_HZ - (time.time() - loop_start)   # cap: at most MAX_HZ inferences/s
                if pause > 0:
                    time.sleep(pause)
            run_s = time.time() - t0
            det.close()
    else:
        print('ATLAS is moving: the benchmark runs only when parked', flush=True)
    res = evaluate(parked, engine_ok, lat, run_s, base, load, stop, missing)
    res['when'] = time.strftime('%Y-%m-%d %H:%M')
    out = Path.home() / '.local/state/project_atlas' / f'yolo_bench_{time.strftime("%Y%m%d_%H%M%S")}.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1))
    try:
        import atlas_master_plan
        atlas_master_plan.record_later(8, res, out.name)
    except Exception as exc:
        print(f'note: master plan not updated ({exc})')
    print(json.dumps(res, indent=1))
    print(f'STEP 8: {res["verdict"]}')
    print(f'saved {out}')


if __name__ == '__main__':
    main()
