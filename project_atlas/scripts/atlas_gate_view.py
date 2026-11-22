"""'What ATLAS sees' (2026-11-22 owner request): read-only view of the mux LiDAR availability gate.

For each of the 72 robot-frame 5-degree directions (0 = forward, counter-clockwise = left, laser origin) it reports
which source covers it, using the SAME functions as the cmd_vel mux (atlas_lidar_availability):

  lidar      a valid LiDAR return in the bin
  astra      Astra depth coverage (fresh /astra/obstacle_coverage)
  ultrasonic a fresh VALID front/rear (and measured corner) ultrasonic reading
  map        no echo, but the saved map + virtual obstacles explain it (AMCL fresh and confident)
  none       nothing covers it -> the gate stops Nav2 if the motion needs this direction

It also reports what the gate would say right now for a straight forward, straight reverse and in-place spin
command. Display only: it never publishes, never commands motion and never changes the gate.
"""
import math

import atlas_lidar_availability as la

PROBE_SPEED_MPS = 0.15
PROBE_SPIN_RADPS = 0.5
US_MAX_AGE_S = 0.5


def ultrasonic_ranges(validity, max_age_s=US_MAX_AGE_S):
    """{'front': m, ...} from the /ultrasonic/validity JSON (dict): VALID and fresh only."""
    out = {}
    for side, s in ((validity or {}).get('sensors') or {}).items():
        try:
            if s.get('state') == 'VALID' and float(s.get('sample_age_s', 99)) <= max_age_s and s.get('range_mm'):
                out[side] = float(s['range_mm']) / 1000.0
        except (TypeError, ValueError, AttributeError):
            continue
    return out


def _us_bins(us, extent):
    front_rear = {k: v for k, v in us.items() if k in la.US_MOUNTS}
    bins = set(la.ultrasonic_covered_bins(front_rear, extent))
    side_fn = getattr(la, 'side_ultrasonic_covered_bins', None)
    mounts = getattr(la, 'SIDE_US_MOUNTS', {}) or {}
    if side_fn and mounts:
        bins |= set(side_fn({k: v for k, v in us.items() if k in mounts}, extent))
    return bins


def _map_ok(pose, xy_std, yaw_std, pose_age_s):
    return (pose is not None and pose_age_s is not None and 0 <= pose_age_s <= la.MAP_POSE_MAX_AGE_S
            and xy_std is not None and xy_std <= la.MAP_POSE_MAX_XY_STD_M
            and yaw_std is not None and yaw_std <= la.MAP_POSE_MAX_YAW_STD_DEG)


def _ray(grid, x, y, ang, max_d=8.0):
    """('wall'|'unknown'|'edge'|'open', distance_m, [x, y]) along a map ray."""
    c, s = math.cos(ang), math.sin(ang)
    d = grid.res * 0.5
    while d <= max_d:
        px, py = x + d * c, y + d * s
        gx, gy = int(math.floor((px - grid.ox) / grid.res)), int(math.floor((py - grid.oy) / grid.res))
        if not (0 <= gx < grid.w and 0 <= gy < grid.h):
            return 'edge', round(d, 2), [round(px, 2), round(py, 2)]
        v = grid.data[gy * grid.w + gx]
        if v >= grid.occ:
            return 'wall', round(d, 2), [round(px, 2), round(py, 2)]
        if v < 0 or v > grid.free:
            return 'unknown', round(d, 2), [round(px, 2), round(py, 2)]
        d += grid.res * 0.5
    return 'open', round(max_d, 2), [round(x + max_d * c, 2), round(y + max_d * s, 2)]


def build(guard, scan, steady_now, ros_now, grid=None, pose=None, xy_std=None, yaw_std=None, pose_age_s=None,
          validity=None):
    """guard: LidarAvailability fed with /scan and /astra/obstacle_coverage. scan: the latest LaserScan (for ranges).
    pose: (x, y, yaw) of base_link in the map. Returns a JSON-ready dict."""
    if guard is None or scan is None:
        return {'state': 'MISSING', 'reason': 'No /scan yet'}
    us = ultrasonic_ranges(validity)
    ext_fwd = la.sweep_extent_cached(PROBE_SPEED_MPS, 0.0)
    astra = set(guard.covered(steady_now))
    us_bins = _us_bins(us, ext_fwd) | _us_bins(us, la.sweep_extent_cached(-PROBE_SPEED_MPS, 0.0))
    map_ready = grid is not None and _map_ok(pose, xy_std, yaw_std, pose_age_s)
    no_echo = set(range(72)) - set(guard.bins)
    explained = set()
    if map_ready and no_echo:
        explained = set(la.map_known_bins(no_echo - astra - us_bins, grid, pose,
                                          obstacles=guard.obstacles(steady_now), extent=ext_fwd))
    # nearest valid LiDAR range per robot bin (laser_frame is yawed 180 deg, like the gate)
    nearest = {}
    for i, r in enumerate(scan.ranges):
        if math.isfinite(r) and scan.range_min <= r <= scan.range_max:
            b = int(((math.degrees(scan.angle_min + i * scan.angle_increment) + guard.yaw_deg) % 360) // 5) % 72
            nearest[b] = min(r, nearest.get(b, float('inf')))
    bins = []
    for b in range(72):
        if b in guard.bins: src = 'lidar'
        elif b in astra: src = 'astra'
        elif b in us_bins: src = 'ultrasonic'
        elif b in explained: src = 'map'
        else: src = 'none'
        item = {'bin': b, 'from_deg': b * 5, 'source': src,
                'lidar_m': round(nearest[b], 2) if b in nearest else None}
        if src != 'lidar' and grid is not None and pose is not None:
            x, y, yaw = pose
            lx, ly = x + la.LASER_X * math.cos(yaw), y + la.LASER_X * math.sin(yaw)
            kind, dist, pt = _ray(grid, lx, ly, yaw + math.radians(b * 5 + 2.5))
            item['map'] = {'hit': kind, 'distance_m': dist, 'point': pt,
                           'heading_deg': round(math.degrees(yaw + math.radians(b * 5 + 2.5)) % 360)}
        bins.append(item)

    def explainer(linear, angular):
        if not map_ready:
            return None
        def explain(missing):
            return la.map_known_bins(missing, grid, pose, obstacles=guard.obstacles(steady_now),
                                     extent=la.sweep_extent_cached(linear, angular))
        return explain

    probes = {}
    for name, (v, w) in (('forward', (PROBE_SPEED_MPS, 0.0)), ('reverse', (-PROBE_SPEED_MPS, 0.0)),
                         ('spin', (0.0, PROBE_SPIN_RADPS))):
        try:
            why = guard.reason(v, w, ros_now, steady_now, explain=explainer(v, w), ultrasonic=us or None)
        except Exception as exc:   # display only; never let the view raise
            why = 'view error: %s' % str(exc)[:80]
        probes[name] = {'ok': why is None, 'reason': why}
    counts = {}
    for it in bins:
        counts[it['source']] = counts.get(it['source'], 0) + 1
    return {'state': 'LIVE', 'bins': bins, 'counts': counts, 'probes': probes,
            'map_fallback': 'ready' if map_ready else ('no map' if grid is None else 'location not confident or stale'),
            'pose': None if pose is None else [round(pose[0], 2), round(pose[1], 2), round(math.degrees(pose[2]))],
            'xy_std_m': None if xy_std is None else round(xy_std, 3),
            'ultrasonic_m': {k: round(v, 2) for k, v in us.items()},
            'limits': {'map_gap_max_bins': la.MAP_GAP_MAX_BINS, 'pose_max_xy_std_m': la.MAP_POSE_MAX_XY_STD_M},
            'note': 'Display only. Same gate functions as the cmd_vel mux; probes are what the gate would say for '
                    'a 0.15 m/s straight or 0.5 rad/s spin command right now.'}
