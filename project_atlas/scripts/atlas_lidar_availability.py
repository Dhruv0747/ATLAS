"""Stop-only scan availability, NOT an obstacle/path-clearance estimator.

No scan alteration. Costmaps still check collision geometry. Five-degree bins
detect unobserved directional sectors; one valid ray is not continuous coverage
or proof of a free swept volume. Turning requires observation in all bins.
"""
import math

class LidarAvailability:
    def __init__(self, timeout_s=.75, frame='laser_frame', yaw_deg=180.):
        self.timeout_s=timeout_s;self.frame=frame;self.yaw_deg=yaw_deg
        self.stamp=None;self.received=None;self.progress=None;self.bins=set()
        self.invalid='no scan'

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
        # Four-wheel steering can sweep both ends/sides. Do not assume that
        # the side opposite requested yaw is irrelevant during an arc.
        if abs(angular)>1e-4:required=set(range(72))
        else:
            centre=0 if linear>0 else 180
            required={i for i in range(72) if abs(((i*5+2.5-centre+180)%360)-180)<=45}
        missing=required-self.bins
        if missing:return f'unobserved motion sector ({len(missing)} bins)'
        return None
