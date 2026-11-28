"""Issue #12 M1: fault-tolerant LOCAL (Jetson) measurement client for one guarded Vision Lab session.

Safety properties (tested offline):
- Starts the session exactly like the dashboard Start button; NEVER sends stop. The session ends by its own 60-s limit
  or by its own guards. If this client dies, its keep-alive stops and the existing 4-s lease stops the camera.
- Every HTTP request is wrapped: a failed or slow request is recorded, never raised.
- Lease renewal runs on its own thread (status every 0.5 s, 2-s timeout), independent of measurement requests.
- The frame counter is a passive subscriber in the PRIVATE domain 77, created only after the viewer is ACTIVE.
  It subscribes with raw=True and reads only the header stamp (no image decode). It never starts a camera driver.
"""
import glob, json, statistics as st, struct, sys, threading, time, urllib.request

BASE = 'http://127.0.0.1:8088'
LEASE_PERIOD_S, LEASE_TIMEOUT_S, RAW_PERIOD_S, RAW_TIMEOUT_S = 0.5, 2.0, 1.0, 3.0


class Http:
    def __init__(self, opener=urllib.request.urlopen, clock=time.monotonic):
        self.open, self.clock, self.log, self.lock = opener, clock, [], threading.Lock()

    def call(self, kind, path, timeout, data=None, headers=None, raw=False):
        """Never raises. Returns (ok, value, seconds)."""
        t = self.clock()
        try:
            req = urllib.request.Request(BASE + path, data=data, headers=headers or {}, method='POST' if data else 'GET')
            with self.open(req, timeout=timeout) as r:
                body = r.read(); hdr = dict(r.headers); code = getattr(r, 'status', 200)
            value = (body, hdr) if raw else json.loads(body)
            ok = True
        except Exception as e:                     # noqa: BLE001  measurement must never crash the client
            value, ok, code = type(e).__name__ + ': ' + str(e)[:80], False, None
        dt = self.clock() - t
        with self.lock: self.log.append({'kind': kind, 'ok': ok, 's': round(dt, 4), 'code': code})
        return ok, value, dt


def cdr_stamp(buf):
    """sensor_msgs/Image CDR: 4-byte encapsulation header, then header.stamp sec (int32), nanosec (uint32)."""
    sec, nsec = struct.unpack_from('<iI', bytes(buf[:12]), 4)
    return sec + nsec * 1e-9


def roi_depth(body, hdr):
    w, h, step = int(hdr['X-Width']), int(hdr['X-Height']), int(hdr['X-Step'])
    if hdr.get('X-Encoding') != '16UC1': return None
    r = max(2, w // 32); cu, cv = w // 2, h // 2
    vals = [struct.unpack_from('<H', body, v * step + 2 * u)[0] for v in range(cv - r, cv + r + 1) for u in range(cu - r, cu + r + 1)]
    good = [x for x in vals if x > 0]
    return {'w': w, 'h': h, 'center_m': st.median(good) / 1000 if good else None, 'valid': len(good) / len(vals)}


class Session:
    def __init__(self, http, sleep=time.sleep, clock=time.monotonic):
        self.http, self.sleep, self.clock = http, sleep, clock
        self.states, self.res, self.depth, self.done = [], [], [], threading.Event()

    def start(self):
        hdrs = {'Content-Type': 'application/json', 'Origin': BASE, 'X-Atlas-Vision3D': '1'}
        return self.http.call('start', '/api/vision3d/viewer', 10, json.dumps({'action': 'start', 'mode': 'depth'}).encode(), hdrs)

    def keepalive(self):
        while not self.done.is_set():
            ok, v, _ = self.http.call('lease', '/api/vision3d/status', LEASE_TIMEOUT_S)
            if ok:
                rt = v.get('runtime') or {}
                self.states.append((round(self.clock(), 2), rt.get('state'), rt.get('reason')))
                if rt.get('resources'): self.res.append(rt['resources'])
                if rt.get('state') not in ('CHECKING', 'ACTIVE') and len(self.states) > 2:
                    self.done.set(); break          # session ended by its own limit or guards
            self.sleep(LEASE_PERIOD_S)

    def measure(self):
        while not self.done.is_set():
            ok, v, _ = self.http.call('raw', '/api/vision3d/raw?kind=depth', RAW_TIMEOUT_S, raw=True)
            if ok:
                try:
                    d = roi_depth(*v)
                    if d: self.depth.append(d)
                except Exception: pass
            self.sleep(RAW_PERIOD_S)


def frame_probe(stop, out):
    import rclpy, rclpy.executors
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import Image
    ctx = rclpy.Context(); rclpy.init(context=ctx, domain_id=77)
    node = rclpy.create_node('m1_local_rate_probe', context=ctx)
    def cb(buf):
        now = time.time(); s = cdr_stamp(buf); out.append((now, s))
    node.create_subscription(Image, '/astra/depth/image_raw', cb, qos_profile_sensor_data, raw=True)
    ex = rclpy.executors.SingleThreadedExecutor(context=ctx); ex.add_node(node)
    while not stop.is_set(): ex.spin_once(timeout_sec=0.1)
    node.destroy_node(); rclpy.shutdown(context=ctx)


def main():
    http = Http(); s = Session(http); frames = []
    gpu = (glob.glob('/sys/devices/platform/bus@0/17000000.gpu/load') or [None])[0]; gpus = []
    ok, v, _ = s.start()
    if not ok or (v.get('state') not in ('CHECKING', 'ACTIVE') if isinstance(v, dict) else True):
        print(json.dumps({'start_refused': v})); return 2
    t0 = time.monotonic()
    threading.Thread(target=s.keepalive, daemon=True).start()
    while time.monotonic() - t0 < 20 and not s.done.is_set() and not any(x[1] == 'ACTIVE' for x in s.states): time.sleep(0.2)
    stop_probe = threading.Event()
    if any(x[1] == 'ACTIVE' for x in s.states):
        threading.Thread(target=s.measure, daemon=True).start()
        threading.Thread(target=frame_probe, args=(stop_probe, frames), daemon=True).start()
    while not s.done.is_set() and time.monotonic() - t0 < 75:
        if gpu:
            try: gpus.append(int(open(gpu).read()) / 10)
            except Exception: pass
        time.sleep(1.0)
    stop_probe.set(); time.sleep(0.5)
    st_ = [f[1] for f in frames]; gaps = [b - a for a, b in zip(st_, st_[1:])]; per = 1 / 30
    lat = sorted(a - b for a, b in frames)
    hist = {}
    for g in gaps: k = int(round(g / per)); hist[k] = hist.get(k, 0) + 1
    def q(xs, p): return round(sorted(xs)[int(p * (len(xs) - 1))], 4) if xs else None
    by = {}
    for r in http.log: by.setdefault(r['kind'], []).append(r)
    out = {'final_state': s.states[-1] if s.states else None, 'states_seen': sorted({x[1] for x in s.states if x[1]}),
           'frames': len(frames), 'distinct_stamps': len(set(st_)),
           'camera_fps': round((len(st_) - 1) / (st_[-1] - st_[0]), 2) if len(st_) > 1 and st_[-1] > st_[0] else None,
           'stream_span_s': round(st_[-1] - st_[0], 1) if len(st_) > 1 else None,
           'gap_hist_periods': hist, 'missed_frames_est': sum(max(0, k - 1) * n for k, n in hist.items()),
           'duplicate_or_near_zero_gaps': hist.get(0, 0), 'max_gap_s': q(gaps, 1.0), 'p95_gap_s': q(gaps, .95),
           'latency_s_p50_p95_max': [q(lat, .5), q(lat, .95), q(lat, 1.0)],
           'depth_center_m_median': round(st.median([d['center_m'] for d in s.depth if d['center_m']]), 4) if s.depth else None,
           'depth_reads': len(s.depth), 'depth_size': (s.depth[0]['w'], s.depth[0]['h']) if s.depth else None,
           'requests': {k: {'n': len(v), 'failed': sum(not x['ok'] for x in v), 'p50_s': q([x['s'] for x in v], .5),
                            'p95_s': q([x['s'] for x in v], .95), 'max_s': q([x['s'] for x in v], 1.0)} for k, v in by.items()},
           'cpu_max': max((r.get('cpu_percent') or 0) for r in s.res) if s.res else None,
           'cpu_mean': round(st.mean([r['cpu_percent'] for r in s.res if r.get('cpu_percent') is not None]), 1) if s.res else None,
           'ram_max': max((r.get('ram_percent') or 0) for r in s.res) if s.res else None,
           'temp_max': max(max((r.get('thermal_c') or {0: 0}).values()) for r in s.res) if s.res else None,
           'gpu_max': max(gpus) if gpus else None, 'stop_sent_by_client': False}
    print(json.dumps(out)); json.dump(out, open('/tmp/m1_local_result.json', 'w'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
