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


def swept_bins(linear, angular):
    """Bins the footprint sweeps into along an arc of radius v/w (ICR at (0, R))."""
    radius = linear / angular
    if abs(radius) < SPIN_RADIUS_M:
        return set(range(72))
    (x0, x1), (y0, y1) = FOOTPRINT_X, FOOTPRINT_Y
    m = SWEEP_MARGIN_M
    dtheta = math.copysign(SWEEP_HORIZON_M / abs(radius), linear * angular) if linear else 0.0
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

class LidarAvailability:
    def __init__(self, timeout_s=.75, frame='laser_frame', yaw_deg=180.):
        self.timeout_s=timeout_s;self.frame=frame;self.yaw_deg=yaw_deg
        self.stamp=None;self.received=None;self.progress=None;self.bins=set()
        self.invalid='no scan'

    def update_coverage(self, msg, now):
        """Astra coverage scan (ranges = seen-clear distance or obstacle range; intensities 1 = obstacle)."""
        self.cover_bins = set(); self.cover_received = None
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
            self.cover_received = now
        except (AttributeError, TypeError, ValueError, OverflowError):
            self.cover_bins = set(); self.cover_received = None

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

    def reason(self, linear, angular, ros_now, steady_now):
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
        if missing:return f'unobserved motion sector ({len(missing)} bins)'
        return None
