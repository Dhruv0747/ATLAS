"""Bound unsolicited AMCL updates by observed odometry progress.

This is not a localization-health verdict or a pose correction. Missing or
stale input never grants an update. Motion watchdogs remain independent.
"""
import math


class AmclUpdateGate:
    def __init__(self, translation_m=0.005, rotation_rad=0.005, max_age_s=0.5):
        if not all(math.isfinite(v) and v > 0 for v in
                   (translation_m, rotation_rad, max_age_s)):
            raise ValueError("update bounds must be positive and finite")
        self.translation_m = translation_m
        self.rotation_rad = rotation_rad
        self.max_age_s = max_age_s
        self.anchor = None
        self.last_stamp = None

    def allow(self, x, y, yaw, stamp_s, now_s):
        values = (x, y, yaw, stamp_s, now_s)
        if not all(math.isfinite(v) for v in values):
            return False
        # A TF's future dating must not be mistaken for fresh motion evidence.
        if not 0 <= now_s - stamp_s <= self.max_age_s:
            return False
        pose = (x, y, yaw)
        if self.last_stamp is not None and stamp_s < self.last_stamp:
            self.anchor, self.last_stamp = pose, stamp_s
            return False
        if self.last_stamp == stamp_s:
            return False
        self.last_stamp = stamp_s
        if self.anchor is None:
            self.anchor = pose
            return False
        dx, dy = x - self.anchor[0], y - self.anchor[1]
        turn = yaw - self.anchor[2]
        turn = abs(math.atan2(math.sin(turn), math.cos(turn)))
        if math.hypot(dx, dy) < self.translation_m and turn < self.rotation_rad:
            return False
        self.anchor = pose
        return True
