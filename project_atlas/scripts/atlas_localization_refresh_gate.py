"""Permit a bounded measurement request, NEVER permission to move."""
import math
from atlas_amcl_update_gate import AmclUpdateGate


class RefreshRequestGate:
    def __init__(self):
        self.progress = AmclUpdateGate()
        self.odom_stamp = None
        self.available = True

    def observe_odom(self, x, y, yaw, stamp_s, now_s):
        if not all(math.isfinite(v) for v in (x,y,yaw,stamp_s,now_s)):
            self.odom_stamp = None
            return
        if not 0 <= now_s-stamp_s <= .5:
            self.odom_stamp = None
            return
        if self.odom_stamp is not None and stamp_s < self.odom_stamp:
            self.available = False
        if self.progress.allow(x,y,yaw,stamp_s,now_s):
            self.available = True
        self.odom_stamp = stamp_s

    def claim(self, processing, now_s, motion_requested, estimate_checks_pass):
        if (not motion_requested or not estimate_checks_pass or not self.available
                or self.odom_stamp is None or not math.isfinite(now_s)
                or not 0 <= now_s-self.odom_stamp <= .5
                or processing.get('processing_state') != 'PROCESSING'):
            return False
        self.available = False
        return True
