#!/usr/bin/env python3
"""Final-map consistency evidence for map acceptance (pure numpy/scipy; no ROS). 2026-11-14, PROPOSAL.

Why: in this house (glass, mirror, open space under furniture in the hall) slam_toolbox corrects map->odom by up to
1.5 m during a drive even though the FINAL map is consistent (remap 10: 3,603 scans fit the final map, median 100 %
within 15 cm, live pose within 24 cm of the best fit). The map->odom jump gate measures those mid-drive frame
corrections, not the quality of the map that would be accepted.

What: during a manual mapping session, sample LiDAR scans together with SLAM's live map->base_link pose. When the
session is stopped, match every sample to the FINAL candidate map (ICP seeded with the live pose) and require that
  * at least ``min_scans`` samples exist and every sample matched,
  * >= ``min_fraction_good`` of samples fit the map with >= ``min_scan_fit`` of their returns within ``tolerance_m``,
  * the live pose was never more than ``max_pose_offset_m`` / ``max_pose_offset_deg`` from the best fit
    (so the rover never believed it was somewhere else while driving).
This module only produces evidence; atlas_map_acceptance_core decides what it may replace (off by default).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np
from scipy.spatial import cKDTree

from atlas_icp_odometry_core import IcpConfig, icp, scan_to_points

SCHEMA = 1


@dataclass(frozen=True)
class FinalMapConsistencyPolicy:
    min_scans: int = 100
    tolerance_m: float = 0.15
    min_scan_fit: float = 0.85
    min_fraction_good: float = 0.95
    max_pose_offset_m: float = 0.30
    max_pose_offset_deg: float = 15.0               # 2026-11-14 owner decision (was 10; remap 13 hall: 13.8)
    sample_period_s: float = 0.5
    max_samples: int = 1200


@dataclass
class ScanSample:
    stamp: float
    pose: Tuple[float, float, float]                 # SLAM live map->base_link (x, y, yaw)
    ranges: np.ndarray
    angle_min: float
    angle_increment: float


@dataclass
class ScanSampleBuffer:
    policy: FinalMapConsistencyPolicy = field(default_factory=FinalMapConsistencyPolicy)
    session_id: Optional[str] = None
    samples: List[ScanSample] = field(default_factory=list)
    dropped: int = 0
    lookup_failures: int = 0
    first_lookup_error: Optional[str] = None

    def begin(self, session_id: str) -> None:
        self.session_id, self.samples, self.dropped = session_id, [], 0
        self.lookup_failures, self.first_lookup_error = 0, None

    def note_lookup_failure(self, error: str) -> None:
        self.lookup_failures += 1
        if self.first_lookup_error is None:
            self.first_lookup_error = error[:200]

    def add(self, stamp, pose, ranges, angle_min, angle_increment) -> bool:
        if self.session_id is None:
            return False
        if self.samples and stamp - self.samples[-1].stamp < self.policy.sample_period_s:
            return False
        if len(self.samples) >= self.policy.max_samples:
            self.samples = self.samples[::2]          # keep coverage of the whole drive, halve density
            self.dropped += 1
        self.samples.append(ScanSample(float(stamp), tuple(float(v) for v in pose),
                                       np.asarray(ranges, dtype=np.float32), float(angle_min), float(angle_increment)))
        return True


def evaluate(samples: Sequence[ScanSample], occupied: np.ndarray, laser_in_base: Tuple[float, float, float],
             policy: FinalMapConsistencyPolicy = FinalMapConsistencyPolicy(), session_id: Optional[str] = None) -> dict:
    """Return evidence: per-sample fit of the scan to the final map and offset of the live pose from the best fit."""
    out = {'schema': SCHEMA, 'session_id': session_id, 'scans': len(samples), 'matched': 0, 'passed': False,
           'failures': [], 'policy': {k: getattr(policy, k) for k in policy.__dataclass_fields__}}
    if len(occupied) < 20:
        out['failures'].append('final map has too few occupied cells')
        return out
    if len(samples) < policy.min_scans:
        out['failures'].append(f'too few scan samples ({len(samples)} < {policy.min_scans})')
        return out
    tree = cKDTree(occupied)
    cfg = IcpConfig(coarse_match_m=0.3, fine_match_m=0.10, min_matches=30, max_points=400)
    mx, my, myaw = laser_in_base
    fits, offs, offs_deg, unmatched = [], [], [], 0
    for s in samples:
        pts = scan_to_points(s.ranges, s.angle_min, s.angle_increment, mx, my, myaw, cfg)
        if len(pts) < cfg.min_matches:
            unmatched += 1
            continue
        r = icp(pts, occupied, (s.pose[2], s.pose[0], s.pose[1]), cfg, tree)
        if not r:
            unmatched += 1
            continue
        dth = math.atan2(math.sin(r[0] - s.pose[2]), math.cos(r[0] - s.pose[2]))
        th = s.pose[2] + dth
        c, sn = math.cos(th), math.sin(th)
        world = pts @ np.array([[c, sn], [-sn, c]]) + [r[1], r[2]]
        d, _ = tree.query(world)
        fits.append(float((d <= policy.tolerance_m).mean()))
        offs.append(math.hypot(r[1] - s.pose[0], r[2] - s.pose[1]))
        offs_deg.append(abs(math.degrees(dth)))
    out['matched'] = len(fits)
    if unmatched:
        out['failures'].append(f'{unmatched} scan sample(s) did not match the final map')
    if not fits:
        return out
    f = np.array(fits)
    good = float((f >= policy.min_scan_fit).mean())
    out.update({'fit_median': round(float(np.median(f)), 4), 'fit_p10': round(float(np.percentile(f, 10)), 4),
                'fraction_good': round(good, 4),
                'pose_offset_median_m': round(float(np.median(offs)), 3), 'pose_offset_max_m': round(max(offs), 3),
                'pose_offset_max_deg': round(max(offs_deg), 2)})
    if good < policy.min_fraction_good:
        out['failures'].append(f'only {good:.1%} of scans fit the final map >= {policy.min_scan_fit:.0%} '
                               f'(need {policy.min_fraction_good:.0%})')
    if max(offs) > policy.max_pose_offset_m:
        out['failures'].append(f'live pose was {max(offs):.2f} m from the final-map fit (max {policy.max_pose_offset_m:.2f})')
    if max(offs_deg) > policy.max_pose_offset_deg:
        out['failures'].append(f'live heading was {max(offs_deg):.1f} deg from the final-map fit '
                               f'(max {policy.max_pose_offset_deg:.1f})')
    out['passed'] = not out['failures']
    return out
