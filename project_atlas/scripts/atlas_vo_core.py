#!/usr/bin/env python3
"""ATLAS camera visual odometry in SHADOW MODE: pure core (numpy/scipy, no ROS). Master-plan step 7, 2026-11-23.

Plan text: "Evaluate camera VO/VIO in shadow mode with rate, age, confidence and GOOD/DEGRADED/LOST states."

Camera choice (2026-11-23): the Astra DEPTH camera, not the IMX708.
  * The Astra already runs at boot in its private ROS domain 77 and turns each validated depth frame
    (factory CameraInfo, measured mount, floor..1.0 m band, stale/blinded frames dropped) into
    /astra/obstacle_scan (base_link, about +-30 deg, up to 10 Hz). Depth is METRIC, so the estimate has scale.
  * The IMX708 is monocular (no metric scale without IMU fusion) and its 1280x720 JPEG stream would need decoding
    and feature tracking: several times the CPU on a Jetson that already runs at load average 10-16.
  * Method: keyframe scan-to-scan point-to-line ICP (keyframe logic and gates of the validated LiDAR ICP core,
    atlas_icp_odometry_core) on the depth camera's planar obstacle scan. It is depth-camera odometry, not feature VIO; no IMU is used, so its heading
    is independent of the IM10A / EKF and can be compared against LiDAR-ICP honestly.

SHADOW MODE: the node publishes only inside domain 77 (/astra/vo/odom, /astra/vo/status) and writes a status file.
Nothing in domain 77 consumes them, the Astra bridge relays only the obstacle scans, and the EKF / Nav2 configs
name no VO topic. The step-7 owner test checks all of this (isolation_texts_ok).

States:
  GOOD      fresh (age <= good_age_s), rate >= min_rate_hz and confidence >= good_confidence
  DEGRADED  still producing estimates but slow, late or low confidence (few points, one flat wall, weak match)
  LOST      no accepted estimate for lost_age_s, or rate < lost_rate_hz
"""
from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import atlas_icp_odometry_core as icpc  # noqa: E402


@dataclass
class VoConfig:
    max_rate_hz: float = 10.0          # processing cap: extra scans are dropped, never queued
    rate_window_s: float = 5.0
    good_age_s: float = 0.5
    lost_age_s: float = 1.5
    min_rate_hz: float = 4.0           # below: DEGRADED
    lost_rate_hz: float = 1.0          # below: LOST
    good_confidence: float = 0.5
    full_points: int = 80              # points at which the point factor reaches 1
    icp: icpc.IcpConfig = field(default_factory=lambda: icpc.IcpConfig(
        range_min_m=0.35, range_max_m=3.0, min_matches=30, min_inlier_fraction=0.6, max_points=200,
        keyframe_yaw_deg=15.0, keyframe_translation_m=0.4, max_step_translation_m=0.10, max_step_yaw_deg=12.0))


def scan_points(ranges, angle_min, angle_increment, cfg: VoConfig):
    """/astra/obstacle_scan is already in base_link (mount 0, 0, 0)."""
    return icpc.scan_to_points(ranges, angle_min, angle_increment, 0.0, 0.0, 0.0, cfg.icp)


def confidence(inlier_fraction, n_points, geom, accept_ratio, cfg: VoConfig):
    """Product of match quality, point count, geometry and recent acceptance; 0..1."""
    pts = min(1.0, n_points / float(cfg.full_points))
    return round(max(0.0, min(1.0, inlier_fraction * pts * geom * accept_ratio)), 3)


def classify(rate_hz, age_s, conf, cfg: VoConfig):
    """GOOD / DEGRADED / LOST. age_s None = no accepted estimate yet."""
    if age_s is None or age_s > cfg.lost_age_s or rate_hz < cfg.lost_rate_hz:
        return 'LOST'
    if age_s > cfg.good_age_s or rate_hz < cfg.min_rate_hz or conf < cfg.good_confidence:
        return 'DEGRADED'
    return 'GOOD'


def line_normals(Q, tree, k=5):
    """Per keyframe point: unit normal of its k-neighbourhood and flatness (minor/major eigenvalue, 0 = a line)."""
    _, idx = tree.query(Q, k=min(k, len(Q)))
    n, flat = np.empty_like(Q), np.empty(len(Q))
    for i, nb in enumerate(idx):
        w, v = np.linalg.eigh(np.cov((Q[nb] - Q[nb].mean(0)).T))
        n[i], flat[i] = v[:, 0], w[0] / max(w[1], 1e-12)
    return n, flat


def icp_point_to_line(P, Q, seed, cfg: icpc.IcpConfig, tree, normals, flat, max_flat=0.1, damping=1e-3):
    """Gauss-Newton ICP, point-to-line for keyframe points on a line (flat < max_flat), point-to-point for corners.
    Returns (th, tx, ty, inlier_fraction, geometry) mapping P (current) into Q (keyframe), or None.
    geometry 0..1 = weakest translation direction of the information matrix (per match, 0.2 -> 1): one straight wall
    or parallel walls only leave translation along them unobservable -> ~0. Damping keeps such a direction at the
    seed instead of letting noise walk it.
    2026-11-23: on the Astra's narrow +-30 deg scan, point-to-point ICP slid along walls (synthetic gentle arc:
    heading -2.0 deg, lateral -0.17 m over 0.37 m); pure point-to-line without corners drifted 0.22 m when parked."""
    if len(P) < cfg.min_matches or len(Q) < cfg.min_matches:
        return None
    th, tx, ty = seed
    near, H = None, None
    for k in range(cfg.iterations):
        c, s = math.cos(th), math.sin(th)
        Pt = P @ np.array([[c, s], [-s, c]]) + [tx, ty]
        dist, idx = tree.query(Pt)
        near = dist < (cfg.coarse_match_m if k < cfg.coarse_iterations else cfg.fine_match_m)
        if near.sum() < cfg.min_matches:
            return None
        dP = np.c_[-s * P[:, 0] - c * P[:, 1], c * P[:, 0] - s * P[:, 1]]
        e = Pt - Q[idx]
        line = near & (flat[idx] < max_flat)
        corner = near & ~line
        nn = normals[idx[line]]
        J = np.r_[np.c_[np.sum(dP[line] * nn, 1), nn],
                  np.c_[dP[corner, 0], np.ones(corner.sum()), np.zeros(corner.sum())],
                  np.c_[dP[corner, 1], np.zeros(corner.sum()), np.ones(corner.sum())]]
        r = np.r_[np.sum(e[line] * nn, 1), e[corner, 0], e[corner, 1]]
        H = J.T @ J
        dx = np.linalg.solve(H + damping * len(r) * np.eye(3), -J.T @ r)
        th, tx, ty = th + dx[0], tx + dx[1], ty + dx[2]
        if k >= cfg.coarse_iterations and np.abs(dx).sum() < cfg.converge_eps:
            break
    lam = float(np.linalg.eigvalsh(H[1:, 1:])[0]) / max(1, int(near.sum()))
    return th, float(tx), float(ty), float(near.mean()), min(1.0, max(0.0, lam / 0.2))


RESET_AFTER_REJECTS = 3        # consecutive rejected scans before the keyframe is replaced (tracking broken)
WEAK_REFRESH_MIN_M, WEAK_REFRESH_MIN_DEG = 0.05, 3.0   # a weak match refreshes the keyframe only after real motion
RESET_DEGRADED_S = 3.0         # after a keyframe reset the pose has lost continuity: at most DEGRADED this long
KEYFRAME_MIN_SIZE_FRAC, SIZE_WINDOW = 0.8, 20   # a keyframe must be a FULL scan (>= 80 % of the recent median)
WARMUP_SCANS, WARMUP_STEADY_FRAC = 5, 0.9  # first keyframe only after 5 scans whose sizes agree within 10 %


class VoOdometry(icpc.IcpOdometry):
    """Point-to-line ICP with the accept/reject gates of the LiDAR ICP odometry, but a robust keyframe policy.
    2026-11-23 16:02 live FAIL (parked, wheels still): the pose jumped 14 cm / 4.8 deg while the state said GOOD.
    Cause: like the LiDAR core, every REJECTED scan and every weak (inliers < 0.75) ACCEPTED scan became the new
    keyframe, so one bad scan (a person in view, a depth glitch) became the reference and later good scans were
    matched against it with its offset (reproduced offline: 5.2 cm / 4.1 deg). Now:
      * a rejected scan is dropped; the keyframe is kept until RESET_AFTER_REJECTS rejects in a row (then reset,
        counted in 'resets', and the state is at most DEGRADED for RESET_DEGRADED_S);
      * a weak accepted match refreshes the keyframe only after >= 5 cm or >= 3 deg of motion since the keyframe.
    2026-11-23 16:10 live capture replay (200 parked scans): 3 PARTIAL scans (52-69 of ~93 points). As the keyframe, one
    biased every match by 2.5-5 cm / 1.1-2.3 deg with no reject at all; with a full keyframe the spread was +-7 mm /
    +-0.2 deg. So only a full scan may become a keyframe, and a full scan replaces a partial keyframe BEFORE matching (the pose is
    not changed by it; otherwise the bias of matches against the partial keyframe stays in the pose).
    Same replay: the sizes ramp 52 -> 69 -> 82 -> 95 points right after the start, and a 82-point scan matched to the
    69-point keyframe gave -3.6 deg that stayed in the pose; hence the warm-up (no estimate until the sizes are steady)."""

    last_geom = 0.0
    consecutive_rejects = 0
    resets = 0
    sizes = None

    def _full(self, points):
        """Record this scan's size; True when it is a full scan (eligible as keyframe)."""
        self.sizes = ((self.sizes or []) + [len(points)])[-SIZE_WINDOW:]
        return len(points) >= KEYFRAME_MIN_SIZE_FRAC * float(np.median(self.sizes))

    def _reject(self, points, full):
        self.rejected += 1
        self.consecutive_rejects += 1
        if self.consecutive_rejects >= RESET_AFTER_REJECTS and full:
            self._new_keyframe(points)
            self.resets += 1
            self.consecutive_rejects = 0
        return self.pose, False

    def update(self, points):
        full = self._full(points)
        if self.key_points is None:                      # warm-up: the scan sizes ramp up after a (re)start
            if len(self.sizes) >= WARMUP_SCANS and min(self.sizes[-WARMUP_SCANS:]) >= WARMUP_STEADY_FRAC * max(self.sizes[-WARMUP_SCANS:]):
                self._new_keyframe(points)
            return self.pose, False
        if full and len(self.key_points) < KEYFRAME_MIN_SIZE_FRAC * len(points):
            self._new_keyframe(points)                   # a full scan replaces a PARTIAL keyframe
            return self.pose, False                      # before any match against it (pose unchanged)
        r = icp_point_to_line(points, self.key_points, self.rel, self.cfg, self.key_tree, self.key_n, self.key_flat)
        if r is None:
            return self._reject(points, full)
        th, tx, ty, inl, geom = r
        self.last_inliers, self.last_geom = inl, geom
        new_pose = icpc.compose(self.key_pose, (th, tx, ty))
        step = math.hypot(new_pose[0] - self.pose[0], new_pose[1] - self.pose[1])
        dyaw = abs(math.degrees(math.atan2(math.sin(new_pose[2] - self.pose[2]), math.cos(new_pose[2] - self.pose[2]))))
        if inl < self.cfg.min_inlier_fraction or step > self.cfg.max_step_translation_m or dyaw > self.cfg.max_step_yaw_deg:
            return self._reject(points, full)
        self.rel, self.pose = (th, tx, ty), new_pose
        self.accepted += 1
        self.consecutive_rejects = 0
        moved = math.hypot(tx, ty) >= WEAK_REFRESH_MIN_M or abs(math.degrees(th)) >= WEAK_REFRESH_MIN_DEG
        if full and (abs(math.degrees(th)) > self.cfg.keyframe_yaw_deg or math.hypot(tx, ty) > self.cfg.keyframe_translation_m
                     or (inl < 0.75 and moved)):
            self._new_keyframe(points)
        return self.pose, True

    def _new_keyframe(self, points):
        super()._new_keyframe(points)
        self.key_n, self.key_flat = line_normals(self.key_points, self.key_tree)


class VoTracker:
    """Feed scans with their sensor stamp (s) and the processing time (s, same clock); read status(now)."""

    def __init__(self, cfg: Optional[VoConfig] = None):
        self.cfg = cfg or VoConfig()
        self.odo = VoOdometry(self.cfg.icp)
        self.frames = []            # (t_processed, accepted)
        self.last_accept_stamp = None
        self.last_conf = 0.0
        self.last_points = 0
        self.last_geom = 0.0
        self.total = 0
        self.reset_t = None
        self.seen_resets = 0

    def update(self, points, stamp_s, now_s):
        self.total += 1
        pose, ok = self.odo.update(np.asarray(points, dtype=float))
        self.frames.append((now_s, ok))
        self._trim(now_s)
        self.last_points = int(len(points))
        if self.odo.resets != self.seen_resets:
            self.seen_resets, self.reset_t = self.odo.resets, now_s
        if ok:
            self.last_accept_stamp = stamp_s
            self.last_geom = self.odo.last_geom
            acc = sum(1 for _, a in self.frames if a) / float(len(self.frames))
            self.last_conf = confidence(self.odo.last_inliers, len(points), self.last_geom, acc, self.cfg)
        return pose, ok

    def _trim(self, now_s):
        lo = now_s - self.cfg.rate_window_s
        self.frames = [f for f in self.frames if f[0] >= lo]

    def status(self, now_s):
        self._trim(now_s)
        acc = [t for t, a in self.frames if a]
        rate = len(acc) / self.cfg.rate_window_s
        age = None if self.last_accept_stamp is None else max(0.0, now_s - self.last_accept_stamp)
        conf = self.last_conf if age is not None and age <= self.cfg.lost_age_s else 0.0
        x, y, yaw = self.odo.pose
        state = classify(rate, age, conf, self.cfg)
        if state == 'GOOD' and self.reset_t is not None and now_s - self.reset_t < RESET_DEGRADED_S:
            state = 'DEGRADED'                           # continuity lost at the reset
        return {'state': state, 'resets': self.odo.resets, 'rate_hz': round(rate, 2),
                'age_s': None if age is None else round(age, 3), 'confidence': conf,
                'points': self.last_points, 'geometry': round(self.last_geom, 3),
                'accepted': self.odo.accepted, 'rejected': self.odo.rejected, 'frames': self.total,
                'pose': [round(x, 4), round(y, 4), round(math.degrees(yaw), 2)]}


# ---- step-7 owner test (tools/perception/vo_shadow_check.py) ------------------------------------------------------
VO_TOPIC_RE = re.compile(r'(/astra)?/vo/|vo_odom|visual_odom', re.I)


def isolation_texts_ok(ekf_texts, nav2_text, bridge_text):
    """True when no EKF config, the Nav2 params or the domain-77 -> 0 bridge names a VO topic."""
    return not any(VO_TOPIC_RE.search(t or '') for t in list(ekf_texts) + [nav2_text, bridge_text])


def wrap_deg(a):
    return (a + 180.0) % 360.0 - 180.0


def arc_compare(vo_start, vo_end, icp_start, icp_end):
    """Per-arc VO vs LiDAR-ICP: heading change and chord distance (frame-independent). Poses: [x, y, yaw_deg] /
    (x, y, yaw_deg). Returns None when either side is missing."""
    if not (vo_start and vo_end and icp_start and icp_end):
        return None
    return {'vo_yaw_deg': round(wrap_deg(vo_end[2] - vo_start[2]), 1),
            'icp_yaw_deg': round(wrap_deg(icp_end[2] - icp_start[2]), 1),
            'vo_dist_m': round(math.hypot(vo_end[0] - vo_start[0], vo_end[1] - vo_start[1]), 3),
            'icp_dist_m': round(math.hypot(icp_end[0] - icp_start[0], icp_end[1] - icp_start[1]), 3)}


PARKED = {'min_samples': 20, 'min_rate_hz': 4.0, 'max_age_p95_s': 0.5, 'min_good_fraction': 0.8,
          'max_drift_m': 0.03, 'max_drift_deg': 1.5, 'max_cpu_pct': 25.0, 'max_wheel_mps': 0.02}
MOTION = {'min_icp_turn_deg': 10.0, 'yaw_tol_deg': 5.0, 'yaw_tol_frac': 0.25, 'dist_tol_m': 0.08,
          'dist_tol_frac': 0.25, 'max_age_days': 7.0}


def _p95(v):
    v = sorted(v)
    return v[min(len(v) - 1, int(math.ceil(0.95 * len(v))) - 1)] if v else None


def evaluate_step7(samples, wheel_speeds, isolation_ok, arcs, arcs_file=None, arcs_age_days=None):
    """Pure; unit-tested.
    samples: VO status dicts read every ~0.5 s while parked (state, rate_hz, age_s, pose, cpu_pct, shadow, domain).
    wheel_speeds: |wheel speed| m/s from the dashboard during the same window (proves ATLAS stood still).
    arcs: per-arc 'vo' dicts recorded by the newest Stage-2 / step-4B turn check (arc_compare + 'state').

    Verdict:
      PASS          shadow VO runs within budget, holds still when parked, and agrees with LiDAR-ICP on both arcs
      NOT USABLE    everything runs and is isolated, but in motion VO disagrees with LiDAR-ICP (evaluation done)
      NEEDS MOTION  parked part OK; no recent turn check with VO data -> run the Stage-2 turn check, then again
      FAIL          VO not running, too slow/late/drifting/CPU-heavy, not isolated, or ATLAS moved while parked
    """
    p, c, notes = PARKED, {}, []
    fresh = [s for s in samples if isinstance(s, dict) and s.get('state')]
    c['vo_running'] = len(fresh) >= p['min_samples'] and any(s.get('state') != 'LOST' for s in fresh)
    c['shadow_only'] = (isolation_ok and bool(fresh)
                        and all(s.get('shadow') is True and str(s.get('domain')) == '77' for s in fresh))
    c['atlas_parked'] = bool(wheel_speeds) and max(abs(v) for v in wheel_speeds) <= p['max_wheel_mps']
    rates = sorted(float(s.get('rate_hz') or 0) for s in fresh)
    ages = [float(s['age_s']) for s in fresh if s.get('age_s') is not None]
    cpus = [float(s['cpu_pct']) for s in fresh if s.get('cpu_pct') is not None]
    good = sum(1 for s in fresh if s.get('state') == 'GOOD') / float(len(fresh)) if fresh else 0.0
    rate_med = rates[len(rates) // 2] if rates else 0.0
    age95 = _p95(ages)
    c['rate_ok'] = rate_med >= p['min_rate_hz']
    c['age_ok'] = age95 is not None and age95 <= p['max_age_p95_s']
    c['mostly_good_parked'] = good >= p['min_good_fraction']
    poses = [s['pose'] for s in fresh if s.get('pose')]
    drift_m = drift_deg = None
    if len(poses) >= 2:
        drift_m = max(math.hypot(q[0] - poses[0][0], q[1] - poses[0][1]) for q in poses)
        drift_deg = max(abs(wrap_deg(q[2] - poses[0][2])) for q in poses)
    c['parked_drift_ok'] = drift_m is not None and drift_m <= p['max_drift_m'] and drift_deg <= p['max_drift_deg']
    cpu_med = sorted(cpus)[len(cpus) // 2] if cpus else None
    c['cpu_within_budget'] = cpu_med is not None and cpu_med <= p['max_cpu_pct']
    parked_ok = all(c.values())

    m = MOTION
    usable = [a for a in (arcs or []) if a and abs(a.get('icp_yaw_deg') or 0) >= m['min_icp_turn_deg']]
    recent = arcs_age_days is not None and arcs_age_days <= m['max_age_days']
    motion = None
    if usable and recent:
        rows = []
        for a in usable:
            iy, vy = a['icp_yaw_deg'], a['vo_yaw_deg']
            idist, vdist = a['icp_dist_m'], a['vo_dist_m']
            rows.append({'yaw_agrees': abs(vy - iy) <= max(m['yaw_tol_deg'], m['yaw_tol_frac'] * abs(iy)),
                         'dist_agrees': abs(vdist - idist) <= max(m['dist_tol_m'], m['dist_tol_frac'] * idist),
                         'not_lost': a.get('state') in ('GOOD', 'DEGRADED')})
        motion = {'arcs': len(rows), 'yaw_agrees': all(r['yaw_agrees'] for r in rows),
                  'dist_agrees': all(r['dist_agrees'] for r in rows), 'not_lost': all(r['not_lost'] for r in rows)}
        c['motion_heading_agrees'] = motion['yaw_agrees']
        c['motion_distance_agrees'] = motion['dist_agrees']
        c['motion_tracking_kept'] = motion['not_lost']
    elif arcs and not recent:
        notes.append('newest turn check with VO data is older than %d days' % m['max_age_days'])

    if not parked_ok:
        verdict = 'FAIL'
    elif motion is None:
        verdict = 'NEEDS MOTION'
    elif motion['arcs'] >= 2 and motion['yaw_agrees'] and motion['dist_agrees'] and motion['not_lost']:
        verdict = 'PASS'
    elif motion['arcs'] >= 2:
        verdict = 'NOT USABLE'
    else:
        verdict = 'NEEDS MOTION'
        notes.append('only %d usable arc (need LEFT and RIGHT)' % motion['arcs'])
    failed = [k for k, v in c.items() if not v]
    measured = {'samples': len(fresh), 'rate_hz_median': round(rate_med, 2),
                'age_s_p95': None if age95 is None else round(age95, 3), 'good_fraction': round(good, 2),
                'parked_drift_m': None if drift_m is None else round(drift_m, 3),
                'parked_drift_deg': None if drift_deg is None else round(drift_deg, 2),
                'cpu_pct_median': cpu_med, 'arcs_file': arcs_file,
                'arcs': [{k: a.get(k) for k in ('vo_yaw_deg', 'icp_yaw_deg', 'vo_dist_m', 'icp_dist_m', 'state')}
                         for a in usable]}
    detail = {
        'PASS': 'shadow VO GOOD when parked (%.1f Hz, p95 age %.2f s, CPU %s %%) and agrees with LiDAR-ICP on %d arcs'
                % (rate_med, age95 or 0, cpu_med, len(usable)),
        'NOT USABLE': 'shadow VO runs and is isolated, but in motion it disagrees with LiDAR-ICP (%s); it stays '
                      'shadow-only' % ', '.join(failed),
        'NEEDS MOTION': 'parked part OK; run the Stage-2 turn check once (it records VO vs LiDAR), then this again',
        'FAIL': 'parked shadow check failed: ' + ', '.join(failed),
    }[verdict]
    return {'verdict': verdict, 'checks': c, 'failed': failed if verdict in ('FAIL', 'NOT USABLE') else [],
            'notes': notes, 'measured': measured, 'detail': detail}
