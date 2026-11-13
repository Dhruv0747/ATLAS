#!/usr/bin/env python3
"""Keyframe scan-to-scan ICP odometry core (pure numpy/scipy, no ROS).

Points are given in base_link (the caller applies the laser mount, e.g. the ATLAS laser faces
backwards: yaw 180 deg). Each scan is matched to the current keyframe, seeded with the previous
relative estimate; a new keyframe is taken after enough motion or a weak match. The output is the
rover's planar pose increment, from which the node publishes body-frame velocity for the EKF.
Validated offline 2026-11-12: ICP translation with IM10A heading drifted 0.20 m over a 12.3 m
mapping drive, versus 1.35 m for the wheel-based EKF.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
from scipy.spatial import cKDTree


@dataclass
class IcpConfig:
    range_min_m: float = 0.15
    range_max_m: float = 6.0
    iterations: int = 30
    coarse_iterations: int = 6
    converge_eps: float = 1e-4             # stop when the update moves < this (m + rad)
    coarse_match_m: float = 0.5
    fine_match_m: float = 0.15
    min_matches: int = 40
    min_inlier_fraction: float = 0.6       # below this: reject the match (no output)
    keyframe_yaw_deg: float = 25.0
    keyframe_translation_m: float = 0.6
    max_step_translation_m: float = 0.25   # per scan; ~2 m/s at 8 Hz, far above ATLAS speeds
    max_step_yaw_deg: float = 20.0
    max_points: int = 400                 # uniform subsample (2026-11-13: LiDAR Boost mode gives ~1040 points)


def scan_to_points(ranges, angle_min, angle_increment, mount_x, mount_y, mount_yaw, cfg: IcpConfig):
    r = np.asarray(ranges, dtype=float)
    a = angle_min + np.arange(len(r)) * angle_increment
    ok = np.isfinite(r) & (r > cfg.range_min_m) & (r < cfg.range_max_m)
    idx = np.nonzero(ok)[0]
    if len(idx) > cfg.max_points:
        idx = idx[np.linspace(0, len(idx) - 1, cfg.max_points).astype(int)]
    lx, ly = r[idx] * np.cos(a[idx]), r[idx] * np.sin(a[idx])
    c, s = math.cos(mount_yaw), math.sin(mount_yaw)
    return np.c_[mount_x + c * lx - s * ly, mount_y + s * lx + c * ly]


def icp(P: np.ndarray, Q: np.ndarray, seed: Tuple[float, float, float], cfg: IcpConfig, tree=None):
    """Find (th, tx, ty) mapping points P (current) into Q (keyframe). Returns (th,tx,ty,inliers) or None."""
    if len(P) < cfg.min_matches or len(Q) < cfg.min_matches:
        return None
    tree = tree or cKDTree(Q)
    th, tx, ty = seed
    m = None
    fine_done = 0
    for k in range(cfg.iterations):
        c, s = math.cos(th), math.sin(th)
        Pt = P @ np.array([[c, s], [-s, c]]) + [tx, ty]
        dist, idx = tree.query(Pt)
        m = dist < (cfg.coarse_match_m if k < cfg.coarse_iterations else cfg.fine_match_m)
        if m.sum() < cfg.min_matches:
            return None
        prev_th = th
        A, B = P[m], Q[idx[m]]
        ca, cb = A.mean(0), B.mean(0)
        H = (A - ca).T @ (B - cb)
        th = math.atan2(H[0, 1] - H[1, 0], H[0, 0] + H[1, 1])
        c, s = math.cos(th), math.sin(th)
        ntx, nty = cb - ca @ np.array([[c, s], [-s, c]])
        moved = abs(ntx - tx) + abs(nty - ty) + abs(th - prev_th) if k else 1.0
        tx, ty = ntx, nty
        if k >= cfg.coarse_iterations:
            fine_done += 1
            if moved < cfg.converge_eps and fine_done >= 2:   # converged: stop early
                break
    return th, float(tx), float(ty), float(m.mean())


def compose(a, r):
    c, s = math.cos(a[2]), math.sin(a[2])
    return (a[0] + c * r[1] - s * r[2], a[1] + s * r[1] + c * r[2], a[2] + r[0])


class IcpOdometry:
    """Feed base_link points per scan; get the pose (x, y, yaw) in the ICP odometry frame."""

    def __init__(self, cfg: Optional[IcpConfig] = None):
        self.cfg = cfg or IcpConfig()
        self.key_pose = (0.0, 0.0, 0.0)
        self.key_points = None
        self.key_tree = None
        self.rel = (0.0, 0.0, 0.0)
        self.pose = (0.0, 0.0, 0.0)
        self.accepted = 0
        self.rejected = 0
        self.last_inliers = 0.0

    def update(self, points: np.ndarray):
        """Return (pose, step_ok). step_ok False means this scan was rejected (no output)."""
        if self.key_points is None:
            self.key_points, self.key_tree = points, cKDTree(points)
            return self.pose, False
        r = icp(points, self.key_points, self.rel, self.cfg, self.key_tree)
        if r is None:
            self.rejected += 1
            self._new_keyframe(points)
            return self.pose, False
        th, tx, ty, inl = r
        self.last_inliers = inl
        new_pose = compose(self.key_pose, (th, tx, ty))
        step = math.hypot(new_pose[0] - self.pose[0], new_pose[1] - self.pose[1])
        dyaw = abs(math.degrees(math.atan2(math.sin(new_pose[2] - self.pose[2]), math.cos(new_pose[2] - self.pose[2]))))
        if inl < self.cfg.min_inlier_fraction or step > self.cfg.max_step_translation_m or dyaw > self.cfg.max_step_yaw_deg:
            self.rejected += 1
            self._new_keyframe(points)     # restart from the last good pose
            return self.pose, False
        self.rel = (th, tx, ty)
        self.pose = new_pose
        self.accepted += 1
        if (abs(math.degrees(th)) > self.cfg.keyframe_yaw_deg
                or math.hypot(tx, ty) > self.cfg.keyframe_translation_m or inl < 0.75):
            self._new_keyframe(points)
        return self.pose, True

    def _new_keyframe(self, points):
        self.key_pose, self.key_points, self.key_tree = self.pose, points, cKDTree(points)
        self.rel = (0.0, 0.0, 0.0)


def body_velocity(prev_pose, pose, dt_s: float):
    """Body-frame (vx, vy, wz) of the step prev_pose -> pose over dt_s."""
    dx, dy = pose[0] - prev_pose[0], pose[1] - prev_pose[1]
    c, s = math.cos(prev_pose[2]), math.sin(prev_pose[2])
    dyaw = math.atan2(math.sin(pose[2] - prev_pose[2]), math.cos(pose[2] - prev_pose[2]))
    return (c * dx + s * dy) / dt_s, (-s * dx + c * dy) / dt_s, dyaw / dt_s
