"""Track A G4 shadow check (read-only, ROS domain 77). Modes: floor | box X Y | watch SECONDS
floor: fits the floor plane (in base_link, configured mount) -> true camera height/pitch/roll estimate.
box:   reports the nearest obstacle near bearing atan2(Y,X) and compares with the tape-measured spot.
watch: records scans; flags transient obstacles (phantom candidates) vs the stable scene."""
import json, math, sys, time
import numpy as np, rclpy, yaml
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image, CameraInfo, LaserScan
from std_msgs.msg import String
R = '/home/jetson/project_atlas'   # run on the Jetson: ROS_DOMAIN_ID=77 python3 tools/track_a/g4_shadow_check.py MODE
sys.path.insert(0, R + '/scripts'); import atlas_astra_obstacle_core as core
cfg = yaml.safe_load(open(R + '/config/astra_obstacles.yaml'))
mode = sys.argv[1]
rclpy.init(); n = rclpy.create_node('track_a_g4_check')
frames, infos, scans, status = [], [], [], []
n.create_subscription(Image, '/astra/depth/image_raw', frames.append, qos_profile_sensor_data)
n.create_subscription(CameraInfo, '/astra/depth/camera_info', infos.append, qos_profile_sensor_data)
n.create_subscription(LaserScan, '/astra/obstacle_scan', scans.append, 10)
n.create_subscription(String, '/astra/obstacle_scan_status', lambda m: status.append(json.loads(m.data)), 10)
def spin(sec, stop=None):
    end = time.monotonic() + sec
    while time.monotonic() < end and not (stop and stop()):
        rclpy.spin_once(n, timeout_sec=0.1)
        if len(frames) > 40: del frames[:-40]
spin(3)
st = status[-1] if status else {}
print('status:', st.get('state'), '| calibration', st.get('calibration'), st.get('calibration_source'), 'nominal', st.get('calibration_nominal'))

def depth_points():
    frames.clear(); spin(6, lambda: len(frames) >= 30)
    c = infos[-1]; cal = core.validate_camera_info(c.width, c.height, c.header.frame_id, list(c.k), list(c.d), c.distortion_model)
    stack = np.stack([np.frombuffer(bytes(f.data), np.uint16).reshape(120, 160) for f in frames]).astype(float)
    stack[stack == 0] = np.nan
    with np.errstate(all='ignore'):
        d = np.nanmedian(stack, axis=0).ravel() * 1e-3
    rays = core.pixel_rays(cal['k'], cal['d'], 160, 120)
    ok = np.isfinite(d) & (d > 0.3)
    P = np.c_[rays * d[:, None], d]
    r, t = core.optical_to_base(cfg['mount'])
    return P @ r.T + t, ok, len(frames)

if mode == 'floor':
    B, ok, nf = depth_points()
    rows = np.repeat(np.arange(120), 160)
    print(f'frames {nf} | valid depth {100*ok.mean():.0f} % | bottom 30 rows valid {100*ok.reshape(120,160)[90:].mean():.0f} %')
    cand = ok & (np.abs(B[:, 2]) < 0.15) & (B[:, 0] > 0.3) & (B[:, 0] < 3.5)
    Q = B[cand]
    print('candidate floor points (|z|<15 cm):', len(Q))
    if len(Q) < 150:
        print('RESULT: NOT ENOUGH FLOOR IN VIEW'); 
    else:
        rng = np.random.default_rng(0); best = None
        for _ in range(2000):
            s = Q[rng.choice(len(Q), 3, replace=False)]
            A = np.c_[s[:, 0], s[:, 1], np.ones(3)]
            try: coef = np.linalg.solve(A, s[:, 2])
            except np.linalg.LinAlgError: continue
            if abs(coef[0]) > 0.15 or abs(coef[1]) > 0.15: continue
            inl = np.abs(Q[:, 0]*coef[0] + Q[:, 1]*coef[1] + coef[2] - Q[:, 2]) < 0.015
            if best is None or inl.sum() > best.sum(): best = inl
        F = Q[best]
        coef, *_ = np.linalg.lstsq(np.c_[F[:, 0], F[:, 1], np.ones(len(F))], F[:, 2], rcond=None)
        res = F[:, 2] - np.c_[F[:, 0], F[:, 1], np.ones(len(F))] @ coef
        ax, ay, c0 = coef
        m = cfg['mount']
        print(json.dumps({'floor_inliers': int(best.sum()), 'floor_x_range_m': [round(float(F[:,0].min()),2), round(float(F[:,0].max()),2)],
              'floor_y_range_m': [round(float(F[:,1].min()),2), round(float(F[:,1].max()),2)], 'fit_rms_mm': round(float(res.std()*1000),1),
              'slope_dz_dx': round(float(ax),4), 'slope_dz_dy': round(float(ay),4), 'floor_height_at_camera_m': round(float(ax*m['x_m'] + ay*m['y_m'] + c0),3)}))
        h_at_cam = ax*m['x_m'] + ay*m['y_m'] + c0
        print(f"ESTIMATE camera height above floor: {m['z_m'] - h_at_cam:.3f} m (configured {m['z_m']})")
        print(f"ESTIMATE pitch nose-down: {m['pitch_deg'] + math.degrees(math.atan(ax)):.2f} deg (configured {m['pitch_deg']})")
        print(f"ESTIMATE roll (left side up +): {math.degrees(math.atan(ay)):.2f} deg (configured 0, not modelled)")
        cut = cfg['obstacle_scan']['min_height_m'] + np.hypot(F[:,0], F[:,1]) * math.tan(math.radians(cfg['obstacle_scan']['floor_margin_deg']))
        print(f"floor points above the obstacle cut (would be phantoms): {int((F[:,2] >= cut).sum())} of {len(F)} | floor z p99 {np.percentile(F[:,2],99):.3f} m")

def scan_summary(label, sc):
    r = np.array(sc.ranges); a = sc.angle_min + np.arange(len(r)) * sc.angle_increment
    print(label, 'obstacle bins', int(np.isfinite(r).sum()), 'of', len(r))
    for name, lo, hi in (('right', -0.53, -0.17), ('centre', -0.17, 0.17), ('left', 0.17, 0.53)):
        m = (a >= lo) & (a < hi) & np.isfinite(r)
        if m.any():
            i = np.argmin(np.where(m, r, np.inf))
            print(f'   {name:6s} nearest {r[i]:.2f} m at {math.degrees(a[i]):+.0f} deg')
        else: print(f'   {name:6s} clear')

if mode == 'scene':
    scans.clear(); spin(3)
    if scans: scan_summary('scene:', scans[-1])
    B, ok, nf = depth_points()
    print(f'valid depth {100*ok.mean():.0f} % | bottom 30 rows valid {100*ok.reshape(120,160)[90:].mean():.0f} % | floor-like points (|z|<5 cm, 0.3-3 m): {int((ok & (np.abs(B[:,2])<0.05) & (B[:,0]>0.3)&(B[:,0]<3)).sum())}')

if mode == 'box':
    X, Y = float(sys.argv[2]), float(sys.argv[3])
    scans.clear(); spin(5)
    want_a = math.atan2(Y, X); hits = []
    for sc in scans:
        r = np.array(sc.ranges); a = sc.angle_min + np.arange(len(r)) * sc.angle_increment
        m = np.abs(a - want_a) < math.radians(4) & np.isfinite(r) if False else (np.abs(a - want_a) < math.radians(4)) & np.isfinite(r)
        if m.any(): hits.append(float(r[m].min()))
    exp = math.hypot(X, Y)
    if not hits: print(f'BOX: NOT DETECTED within +-4 deg of {math.degrees(want_a):+.1f} deg ({len(scans)} scans)')
    else:
        med = float(np.median(hits)); print(f'BOX: detected in {len(hits)}/{len(scans)} scans | measured range {med:.3f} m (std {np.std(hits)*1000:.1f} mm) | tape {exp:.3f} m | error {(med-exp)*100:+.1f} cm -> {"PASS" if abs(med-exp) <= 0.03 else "FAIL"} (limit 3 cm)')
    if scans: scan_summary('scene:', scans[-1])

if mode == 'watch':
    dur = float(sys.argv[2]); scans.clear(); status.clear(); t0 = time.monotonic(); spin(dur)
    if not scans: print('WATCH: no scans'); sys.exit()
    Rm = np.array([sc.ranges for sc in scans], dtype=float)
    fin = np.isfinite(Rm); occ = fin.mean(axis=0)
    base = np.where(occ > 0.5, np.nanmedian(np.where(fin, Rm, np.nan), axis=0), np.inf)
    # phantom candidate: a hit clearly NEARER (>15 cm) than the stable scene in that bin (or in a normally empty bin)
    with np.errstate(invalid='ignore'):
        nearer = fin & (Rm < base[None, :] - 0.15)
    per_scan = nearer.sum(axis=1)
    states = {}
    for s in status: states[s['state']] = states.get(s['state'], 0) + 1
    print(json.dumps({'duration_s': round(time.monotonic()-t0), 'scans': len(scans), 'hz': round(len(scans)/dur, 2),
          'stable_obstacle_bins': int((occ > 0.5).sum()), 'empty_bins': int((occ == 0).sum()),
          'scans_with_phantom_candidates': int((per_scan > 0).sum()), 'max_phantom_bins_in_one_scan': int(per_scan.max()),
          'phantom_bin_hits_total': int(nearer.sum()), 'status_counts': states,
          'stable_scene_jitter_mm_median': round(float(np.nanmedian(np.nanstd(np.where(fin[:, occ > 0.5], Rm[:, occ > 0.5], np.nan), axis=0)))*1000, 1) if (occ>0.5).any() else None}))
    if nearer.any():
        a = scans[0].angle_min + np.arange(Rm.shape[1]) * scans[0].angle_increment
        idx = np.argwhere(nearer)
        print('phantom candidate bins (deg: count, nearest m):', {f'{math.degrees(a[j]):+.0f}': (int(nearer[:, j].sum()), round(float(Rm[nearer[:, j], j].min()), 2)) for j in np.unique(idx[:, 1])[:15]})
rclpy.shutdown()
