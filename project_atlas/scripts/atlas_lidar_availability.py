"""Stop-only scan availability, NOT an obstacle/path-clearance estimator.

No scan alteration. Costmaps still check collision geometry. Five-degree bins
detect unobserved directional sectors; one valid ray is not continuous coverage
or proof of a free swept volume.

2026-11-15 swept-path policy (owner-approved design; replaces "every arc needs all
72 bins", which blocked 66 % of real scans): straight motion needs the +/-45 deg
travel cone (unchanged); spinning or arcs tighter than SPIN_RADIUS_M still need all
bins; any other arc needs the travel cone PLUS every bin that the rover footprint
sweeps into (outside its current outline by > SWEEP_MARGIN_M) within
SWEEP_HORIZON_M of path, assuming the opposite-phase 4WS ICR on the base_link
lateral axis, widened by one bin each side. Invalid ranges are still never free.
"""
import math

# base_link footprint (nav2_params.yaml) and laser origin (tf base_link->laser_frame)
FOOTPRINT_X = (-0.25, 0.25)
FOOTPRINT_Y = (-0.18, 0.18)
LASER_X = -0.05
SWEEP_HORIZON_M = 0.5
SWEEP_MARGIN_M = 0.02
SPIN_RADIUS_M = 0.35
TRAVEL_CONE_DEG = 45.0
# 2026-11-15 fused coverage: a LiDAR bin with no return counts as observed only if the Astra depth coverage
# (/astra/obstacle_coverage, base_link, see atlas_astra_obstacle_core) saw it: an obstacle there, or the floor seen
# clear at least COVER_CLEAR_M from the laser across the whole bin. Never turns "no data" into free space.
COVER_CLEAR_M = 0.8
COVER_TIMEOUT_S = 0.75


# 2026-11-16 map-known gaps (owner-approved idea: "if the laser does not come back but the location is > 3 m away,
# use the map"). Stage-3 hall drives: 69-83 % of moving scans were vetoed by 1-3 no-echo bins whose rays, cast on
# the accepted map, ended on the SAME three static wall spots in both runs (surfaces that do not return the RPLIDAR
# beam). A missing bin counts as explained only when ALL of these hold:
#   - AMCL is fresh and confident (pose age, xy and yaw std below the limits below);
#   - at most MAP_GAP_MAX_BINS bins are missing after the Astra coverage (a mostly blind scan still stops);
#   - every sub-ray of the bin, cast from the laser on the occupancy map, crosses only FREE cells and ends on an
#     OCCUPIED cell no closer than MAP_GAP_MIN_M (unknown cells, map edge or no wall within MAP_GAP_RAY_MAX_M fail).
# Residual risk (documented, owner decision): an obstacle that ALSO returns no echo, standing inside such a gap.
MAP_GAP_MIN_M = 0.4          # 2026-11-16 owner decision ("1 m -> 0.4"); replay vetoes at 0.45 m: 84->26 %, 69->28 %, 83->11 % (1.0 m: 79/35/38 %)
MAP_GAP_MAX_BINS = 3
MAP_GAP_RAY_MAX_M = 6.0
MAP_POSE_MAX_AGE_S = 3.0
MAP_POSE_MAX_XY_STD_M = 0.15
MAP_POSE_MAX_YAW_STD_DEG = 10.0
# 2026-11-16 owner: "if the camera sees something closer, stop" — a bin is never map-explained when fresh Astra depth
# shows an obstacle in that bin closer than the mapped wall minus this margin (stage-3 #3 replay: 10 of 4990).
MAP_GAP_CAMERA_MARGIN_M = 0.15
# 2026-11-16 sweep-aware clearance (owner: "nice idea, apply it"): instead of one fixed distance for every bin, a
# map-explained bin needs its mapped wall beyond how far the rover body actually reaches into that bin during the
# next SWEEP_EXTENT_HORIZON_M of travel along the commanded arc, plus SWEEP_EXTENT_MARGIN_M, and never closer than
# MAP_GAP_FLOOR_M. Spot A (stage-3 #4): wall 0.35 m on the side the rear swings into while turning -> still vetoed.
SWEEP_EXTENT_HORIZON_M = 0.25
SWEEP_EXTENT_MARGIN_M = 0.05          # owner decision 2026-11-16 (replay: 2340 vetoed scans vs 3377 fixed 0.4 m, 3528 at 0.10)
MAP_GAP_FLOOR_M = 0.25


class OccGrid:
    """Minimal occupancy grid: data row-major from the origin (nav_msgs/OccupancyGrid layout), -1 unknown,
    0..100 occupancy. Origin rotation is assumed 0 (map_server maps)."""
    def __init__(self, width, height, resolution, origin_x, origin_y, data, occupied=65, free=25):
        if width <= 0 or height <= 0 or resolution <= 0 or len(data) != width * height:
            raise ValueError('bad occupancy grid')
        self.w, self.h, self.res = int(width), int(height), float(resolution)
        self.ox, self.oy = float(origin_x), float(origin_y)
        self.data, self.occ, self.free = data, occupied, free

    @classmethod
    def from_msg(cls, msg):
        o = msg.info.origin
        if abs(o.orientation.z) > 1e-6 or abs(o.orientation.x) > 1e-6 or abs(o.orientation.y) > 1e-6:
            raise ValueError('rotated map origin not supported')
        return cls(msg.info.width, msg.info.height, msg.info.resolution, o.position.x, o.position.y, list(msg.data))

    def first_wall(self, x, y, angle, max_d):
        """Distance to the first occupied cell along the ray, or None if the ray meets unknown space, leaves the
        map or finds no wall within max_d."""
        c, s = math.cos(angle), math.sin(angle)
        step = self.res * 0.5
        d = step
        while d <= max_d:
            gx = int(math.floor((x + d * c - self.ox) / self.res))
            gy = int(math.floor((y + d * s - self.oy) / self.res))
            if not (0 <= gx < self.w and 0 <= gy < self.h):
                return None
            v = self.data[gy * self.w + gx]
            if v >= self.occ:
                return d
            if v < 0 or v > self.free:
                return None
            d += step
        return None


def _laser_dist(x, y):
    return math.hypot(x - LASER_X, y)


_EXTENT_CACHE = {}


def sweep_extent_cached(linear, angular):
    """sweep_extent rounded to 0.01 m/s and 0.02 rad/s, memoised (the mux asks at 20 Hz; 2026-11-16 the uncached
    version cost the mux ~26 % CPU). Bounded cache."""
    if not (math.isfinite(linear) and math.isfinite(angular)):
        return sweep_extent(linear, angular)
    key = (round(linear, 2), round(angular / 0.02) * 0.02)
    ext = _EXTENT_CACHE.get(key)
    if ext is None:
        if len(_EXTENT_CACHE) > 512:
            _EXTENT_CACHE.clear()
        ext = _EXTENT_CACHE[key] = sweep_extent(key[0], key[1])
    return ext


def sweep_extent(linear, angular, horizon=SWEEP_EXTENT_HORIZON_M):
    """{bin: farthest distance from the laser that the rover footprint occupies in that bin}, now and along the
    commanded motion for `horizon` metres of travel (arc about the 4WS ICR (0, v/w), or straight). Every bin gets at
    least the current outline distance."""
    ext = {}
    for px, py in _OUTLINE:
        b = _bin(px, py); ext[b] = max(ext.get(b, 0.0), _laser_dist(px, py))
    if not (math.isfinite(linear) and math.isfinite(angular)) or abs(linear) < 1e-4:
        return ext
    straight = abs(angular) < 1e-4 or abs(linear / angular) > 50.0
    steps = 20
    for k in range(1, steps + 1):
        s_ = horizon * k / steps
        if straight:
            dx = math.copysign(s_, linear)
            pts = [(px + dx, py) for px, py in _OUTLINE]
        else:
            radius = linear / angular
            th = math.copysign(s_ / abs(radius), linear * angular)
            c, sn = math.cos(th), math.sin(th)
            pts = [(c * px - sn * (py - radius), sn * px + c * (py - radius) + radius) for px, py in _OUTLINE]
        for qx, qy in pts:
            b = _bin(qx, qy); d = _laser_dist(qx, qy)
            if d > ext.get(b, 0.0):
                ext[b] = d
    return ext


def required_wall_distance(b, extent):
    """Minimum mapped-wall distance (from the laser) for bin b to be map-explained."""
    reach = max(extent.get(b, 0.0), extent.get((b - 1) % 72, 0.0), extent.get((b + 1) % 72, 0.0))
    return max(MAP_GAP_FLOOR_M, reach + SWEEP_EXTENT_MARGIN_M)


def map_known_bins(missing, grid, pose, min_dist=MAP_GAP_MIN_M, max_d=MAP_GAP_RAY_MAX_M, obstacles=None,
                   extent=None):
    """Subset of the missing robot-frame bins whose every sub-ray hits a mapped wall at >= min_dist through free
    space. pose = (x, y, yaw) of base_link in the map frame. obstacles: optional {bin: distance from the laser} of
    fresh camera obstacles; a bin with a camera obstacle closer than its mapped wall (minus a margin) is never
    explained. extent: optional sweep_extent(); when given, each bin's minimum wall distance is
    required_wall_distance(bin, extent) instead of the fixed min_dist."""
    x, y, yaw = pose
    lx, ly = x + LASER_X * math.cos(yaw), y + LASER_X * math.sin(yaw)
    known = set()
    for b in missing:
        ok = True
        nearest = float('inf')
        need = required_wall_distance(b, extent) if extent is not None else min_dist
        for f in (0.5, 1.5, 2.5, 3.5, 4.5):
            d = grid.first_wall(lx, ly, yaw + math.radians(b * 5 + f), max_d)
            if d is None or d < need:
                ok = False
                break
            nearest = min(nearest, d)
        if ok and obstacles:
            cam = obstacles.get(b)
            if cam is not None and cam < nearest - MAP_GAP_CAMERA_MARGIN_M:
                ok = False
        if ok:
            known.add(b)
    return known


def _outline(step=0.025):
    (x0, x1), (y0, y1) = FOOTPRINT_X, FOOTPRINT_Y
    nx, ny = int(round((x1 - x0) / step)), int(round((y1 - y0) / step))
    pts = [(x0 + (x1 - x0) * i / nx, y) for i in range(nx + 1) for y in (y0, y1)]
    pts += [(x, y0 + (y1 - y0) * j / ny) for j in range(1, ny) for x in (x0, x1)]
    return pts


_OUTLINE = _outline()


def _bin(x, y):
    return int((math.degrees(math.atan2(y, x - LASER_X)) % 360.0) // 5) % 72


def travel_cone(linear):
    """Bins the footprint sweeps into when translating straight SWEEP_HORIZON_M (+/-1 bin), plus the
    +/-5 deg dead-ahead bins. 2026-11-15: replaces the fixed +/-45 deg cone; from the laser origin the 0.36 m wide
    body sweeps about +/-31 deg (bumper corners) narrowing to +/-13 deg at 0.5 m ahead."""
    (x0, x1), (y0, y1) = FOOTPRINT_X, FOOTPRINT_Y
    m = SWEEP_MARGIN_M
    sign = 1.0 if linear > 0 else -1.0
    out = set()
    for k in range(1, 26):
        dx = sign * SWEEP_HORIZON_M * k / 25
        for px, py in _OUTLINE:
            qx = px + dx
            if x0 - m <= qx <= x1 + m and y0 - m <= py <= y1 + m:
                continue
            b = _bin(qx, py)
            out.update({(b - 1) % 72, b, (b + 1) % 72})
    centre = 0 if linear > 0 else 36
    out.update({(centre - 1) % 72, centre, (centre + 1) % 72})
    return out


# 2026-11-16 (hall door, stage-3 #5: 63 % of commands were arcs tighter than SPIN_RADIUS_M, each demanding all 72
# bins): when False, tight arcs require only the bins the footprint actually sweeps (rotation capped at one full
# turn), like wider arcs. Pure in-place spins (|v| ~ 0) always require all bins. Default keeps the old policy.
TIGHT_ARC_FULL_RING = False          # owner decision 2026-11-16 ("pehle fixes deploy"); replay #3 29 -> 20 %


def swept_bins(linear, angular):
    """Bins the footprint sweeps into along an arc of radius v/w (ICR at (0, R))."""
    radius = linear / angular
    if abs(radius) < SPIN_RADIUS_M and (TIGHT_ARC_FULL_RING or abs(linear) < 1e-4):
        return set(range(72))
    (x0, x1), (y0, y1) = FOOTPRINT_X, FOOTPRINT_Y
    m = SWEEP_MARGIN_M
    dtheta = math.copysign(min(2 * math.pi, SWEEP_HORIZON_M / abs(radius)), linear * angular) if linear else 0.0
    steps = max(4, int(abs(dtheta) / 0.02))
    out = set()
    for k in range(1, steps + 1):
        th = dtheta * k / steps
        c, s = math.cos(th), math.sin(th)
        for px, py in _OUTLINE:
            rx, ry = px, py - radius                     # about the ICR (0, radius)
            qx, qy = c * rx - s * ry, s * rx + c * ry + radius
            if x0 - m <= qx <= x1 + m and y0 - m <= qy <= y1 + m:
                continue                                 # still inside the current outline
            b = _bin(qx, qy)
            out.update({(b - 1) % 72, b, (b + 1) % 72})
    return out

# 2026-11-16 front/rear ultrasonic coverage (owner: "A and B"). Ultrasonic ranging sees glass and black surfaces that
# return no LiDAR echo. Live check 2026-11-16: front/rear VALID at 3.4 Hz, ~0.4 s sample age, within ~7-11 cm of LiDAR
# after the mount offset; left/right are not installed. A bin inside a sensor's cone counts as observed only when the
# sensor reports a fresh VALID range that is clear beyond the footprint reach in that bin (required_wall_distance).
# A short range (something close) never covers anything: the bin stays vetoed.
US_MOUNTS = {'front': (FOOTPRINT_X[1], 0.0, 0.0), 'rear': (FOOTPRINT_X[0], 0.0, 180.0)}   # base_link x, y, axis deg
US_HALF_CONE_DEG = 10.0


def ultrasonic_covered_bins(ranges, extent):
    """ranges: {'front'|'rear': metres from the sensor (fresh, VALID only)}. Returns robot-frame bins (5 deg, laser
    origin) whose whole span lies within a sensor cone and whose clear distance from the laser reaches the
    sweep-aware requirement."""
    out = set()
    for side, r in (ranges or {}).items():
        mount = US_MOUNTS.get(side)
        if mount is None or not isinstance(r, (int, float)) or not math.isfinite(r) or r <= 0:
            continue
        mx, my, axis = mount
        offset = math.hypot(mx - LASER_X, my)                       # laser -> sensor along the axis
        for b in range(72):
            lo, hi = b * 5.0, b * 5.0 + 5.0
            d_lo = (lo - axis + 180.0) % 360.0 - 180.0
            d_hi = (hi - axis + 180.0) % 360.0 - 180.0
            if not (abs(d_lo) <= US_HALF_CONE_DEG and abs(d_hi) <= US_HALF_CONE_DEG):
                continue
            worst = max(abs(d_lo), abs(d_hi))
            clear_from_laser = offset * math.cos(math.radians(worst)) + r
            if clear_from_laser >= required_wall_distance(b, extent):
                out.add(b)
    return out


class LidarAvailability:
    def __init__(self, timeout_s=.75, frame='laser_frame', yaw_deg=180.):
        self.timeout_s=timeout_s;self.frame=frame;self.yaw_deg=yaw_deg
        self.stamp=None;self.received=None;self.progress=None;self.bins=set()
        self.invalid='no scan'

    def update_coverage(self, msg, now):
        """Astra coverage scan (ranges = seen-clear distance or obstacle range; intensities 1 = obstacle)."""
        self.cover_bins = set(); self.cover_received = None; self.cover_obstacles = {}
        try:
            if msg.header.frame_id != 'base_link' or not msg.ranges or msg.angle_increment <= 0:
                return
            n = len(msg.ranges); inten = list(msg.intensities) if len(msg.intensities) == n else [0.0] * n
            def ok(bearing_deg):
                # point COVER_CLEAR_M from the laser at this robot-frame bearing, seen from base_link
                x = LASER_X + COVER_CLEAR_M * math.cos(math.radians(bearing_deg))
                y = COVER_CLEAR_M * math.sin(math.radians(bearing_deg))
                k = int(math.floor((math.atan2(y, x) - msg.angle_min) / msg.angle_increment))
                if not 0 <= k < n:
                    return False
                r = msg.ranges[k]
                if not math.isfinite(r):
                    return False
                return inten[k] >= 0.5 or r >= math.hypot(x, y)
            for b in range(72):
                if all(ok(b * 5 + f) for f in (0.0, 1.25, 2.5, 3.75, 5.0)):
                    self.cover_bins.add(b)
            obst = {}
            for k in range(n):                     # camera obstacles per LiDAR bin, distance from the laser origin
                r = msg.ranges[k]
                if inten[k] >= 0.5 and math.isfinite(r):
                    a = msg.angle_min + k * msg.angle_increment
                    x, y = r * math.cos(a), r * math.sin(a)
                    b = _bin(x, y); d = math.hypot(x - LASER_X, y)
                    obst[b] = min(d, obst.get(b, float('inf')))
            self.cover_obstacles = obst
            self.cover_received = now
        except (AttributeError, TypeError, ValueError, OverflowError):
            self.cover_bins = set(); self.cover_received = None; self.cover_obstacles = {}

    def obstacles(self, steady_now):
        """Fresh camera obstacles {LiDAR bin: distance from the laser}; {} when coverage is stale or missing."""
        rx = getattr(self, 'cover_received', None)
        if rx is None or not 0 <= steady_now - rx <= COVER_TIMEOUT_S:
            return {}
        return dict(getattr(self, 'cover_obstacles', {}))

    def covered(self, steady_now):
        rx = getattr(self, 'cover_received', None)
        if rx is None or not 0 <= steady_now - rx <= COVER_TIMEOUT_S:
            return set()
        return self.cover_bins

    def update(self, scan, now):
        self.received=now;self.bins=set();self.invalid='invalid scan'
        try:
            stamp=scan.header.stamp.sec+scan.header.stamp.nanosec*1e-9
            metadata=(scan.range_min,scan.range_max,scan.angle_min,scan.angle_increment,stamp)
            if (scan.header.frame_id!=self.frame or not all(math.isfinite(x) for x in metadata)
                or stamp<=0 or not 0<=scan.range_min<scan.range_max
                or scan.angle_increment==0 or not scan.ranges):return
            if self.stamp is None or stamp>self.stamp:self.progress=now
            elif stamp<self.stamp:return
            self.stamp=stamp
            for i,d in enumerate(scan.ranges):
                if math.isfinite(d) and scan.range_min<=d<=scan.range_max:
                    angle=(math.degrees(scan.angle_min+i*scan.angle_increment)+self.yaw_deg)%360
                    self.bins.add(int(angle//5)%72)
            self.invalid=None
        except (AttributeError,TypeError,ValueError,OverflowError):return

    def reason(self, linear, angular, ros_now, steady_now, explain=None, ultrasonic=None):
        """explain: optional callable(missing_bins) -> bins explained by the map (see map_known_bins); only
        consulted when at most MAP_GAP_MAX_BINS bins are missing."""
        if not math.isfinite(linear) or not math.isfinite(angular):return 'invalid command'
        if abs(linear)+abs(angular)<1e-4:return None
        if self.invalid:return self.invalid
        if not (0<=steady_now-self.received<=self.timeout_s
                and 0<=steady_now-self.progress<=self.timeout_s
                and 0<=ros_now-self.stamp<=self.timeout_s):return 'scan stale or timestamp invalid'
        # Four-wheel steering can sweep both ends/sides: arcs require the bins the
        # footprint actually sweeps into (see swept_bins), spins require all bins.
        if abs(angular)>1e-4 and abs(linear)<1e-4:required=set(range(72))
        elif abs(angular)>1e-4:required=travel_cone(linear)|swept_bins(linear,angular)
        else:required=travel_cone(linear)
        missing=required-self.bins-self.covered(steady_now)
        self.ultrasonic_explained=0
        if missing and ultrasonic:
            try:
                us=ultrasonic_covered_bins(ultrasonic, sweep_extent_cached(linear, angular))&missing
            except Exception:
                us=set()
            self.ultrasonic_explained=len(us)
            missing=missing-us
        self.map_explained=0
        if missing and explain is not None and len(missing)<=MAP_GAP_MAX_BINS:
            try:
                known=set(explain(set(missing)) or ())&missing
            except Exception:
                known=set()
            self.map_explained=len(known)
            missing=missing-known
        if missing:return f'unobserved motion sector ({len(missing)} bins)'
        return None
