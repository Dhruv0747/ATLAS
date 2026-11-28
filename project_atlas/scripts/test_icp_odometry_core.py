#!/usr/bin/env python3
"""Synthetic tests for atlas_icp_odometry_core: a rectangular room with a box, simulated 360-beam scans."""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from atlas_icp_odometry_core import IcpOdometry, body_velocity, scan_to_points  # noqa: E402

SEGS = [((-2, -1.5), (4, -1.5)), ((4, -1.5), (4, 1.5)), ((4, 1.5), (-2, 1.5)), ((-2, 1.5), (-2, -1.5)),
        ((1, 0.6), (1.6, 0.6)), ((1.6, 0.6), (1.6, 1.0)), ((1.6, 1.0), (1, 1.0)), ((1, 1.0), (1, 0.6))]
AMIN, AINC, N = -math.pi, 2 * math.pi / 360, 360
MOUNT = (-0.05, 0.0, math.pi)   # ATLAS: laser 5 cm behind base_link, facing backwards


def ray(px, py, a):
    best = np.inf
    dx, dy = math.cos(a), math.sin(a)
    for (x1, y1), (x2, y2) in SEGS:
        ex, ey = x2 - x1, y2 - y1; den = dx * ey - dy * ex
        if abs(den) < 1e-12: continue
        t = ((x1 - px) * ey - (y1 - py) * ex) / den; u = ((x1 - px) * dy - (y1 - py) * dx) / den
        if t > 0 and 0 <= u <= 1: best = min(best, t)
    return best


def scan_at(x, y, yaw, rng=None):
    lx = x + math.cos(yaw) * MOUNT[0]; ly = y + math.sin(yaw) * MOUNT[0]; lyaw = yaw + MOUNT[2]
    r = np.array([ray(lx, ly, lyaw + AMIN + i * AINC) for i in range(N)])
    if rng is not None: r = r + rng.normal(0, 0.01, N)
    return r


class IcpOdometryTest(unittest.TestCase):
    def run_path(self, path, noise=True):
        rng = np.random.default_rng(1) if noise else None
        o = IcpOdometry(); oks = 0
        for x, y, yaw in path:
            pts = scan_to_points(scan_at(x, y, yaw, rng), AMIN, AINC, *MOUNT, o.cfg)
            pose, ok = o.update(pts); oks += ok
        return o.pose, oks

    def test_still(self):
        pose, _ = self.run_path([(0, 0, 0)] * 30)
        self.assertLess(math.hypot(pose[0], pose[1]), 0.02); self.assertLess(abs(math.degrees(pose[2])), 0.5)

    def test_forward_2m_backwards_mounted_laser(self):
        path = [(0.02 * i, 0.0, 0.0) for i in range(101)]      # 2 m forward at 0.16 m/s, 8 Hz
        pose, oks = self.run_path(path)
        self.assertGreater(oks, 90)
        self.assertAlmostEqual(pose[0], 2.0, delta=0.06)        # forward, not backward
        self.assertLess(abs(pose[1]), 0.05)

    def test_turn_then_drive(self):
        path = [(0, 0, math.radians(2 * i)) for i in range(46)]                 # turn left 90 deg
        path += [(0, 0.015 * i, math.pi / 2) for i in range(1, 61)]             # 0.9 m forward (+y)
        pose, _ = self.run_path(path)
        self.assertAlmostEqual(math.degrees(pose[2]), 90, delta=2.0)
        self.assertAlmostEqual(pose[1], 0.9, delta=0.06); self.assertLess(abs(pose[0]), 0.06)

    def test_body_velocity(self):
        vx, vy, wz = body_velocity((0, 0, math.pi / 2), (0, 0.1, math.pi / 2), 0.5)
        self.assertAlmostEqual(vx, 0.2, places=6); self.assertAlmostEqual(vy, 0.0, places=6)

    def test_blinded_scan_rejected(self):
        o = IcpOdometry()
        o.update(scan_to_points(scan_at(0, 0, 0), AMIN, AINC, *MOUNT, o.cfg))
        _, ok = o.update(np.zeros((5, 2)))
        self.assertFalse(ok)


if __name__ == '__main__':
    unittest.main(verbosity=2)
