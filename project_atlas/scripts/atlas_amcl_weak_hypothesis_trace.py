#!/usr/bin/env python3
"""Trace survival of the low-weight room hypothesis through saved AMCL clouds.

Read-only offline analysis of ``amcl_roundtrip_20261009_final``. No ROS node,
publisher, service, initial pose, parameter or actuator is created or changed.

The likelihood function reproduces nav2_amcl 1.1.20 ``LikelihoodFieldModel``
(beam step, max-range skip, range-min handling, map validity, sum of cubed
beam probabilities) with the deployed parameters. Published clouds contain
post-resample weights only, so per-particle likelihoods here are recomputed,
not AMCL's internal pre-resample trace. The resampling experiment reproduces
nav2_amcl's multinomial ("naive discrete event") sampler with the observed
KLD sample counts and frozen poses (zero odometry while stopped); it is a
mechanism test, not an AMCL replay or a candidate configuration.
"""
import argparse
import json
import math
from pathlib import Path
import sqlite3

import numpy as np

BAG_NAME = 'amcl_roundtrip_20261009_final'
# Locked from ATLAS_COMPETING_POSE_EVIDENCE_2026-10-09.md (commit 21b8752):
# equal bounded refinement on the +352.107 s scan, map metres / radians.
REFINED_ROOM = (0.37479, -1.16681, 1.38742)
REFINED_FALSE = (4.05178, -0.56237, 3.09811)
LATE_FALSE_ANCHOR = (3.84039193, -0.48244301, 2.72681390)
# Deployed AMCL parameters (nav2_params.yaml; deployed SHA-256 24620bf4...,
# repository copy identical apart from line endings).
AMCL = {'z_hit': 0.5, 'z_rand': 0.5, 'sigma_hit': 0.2, 'max_beams': 60,
        'laser_likelihood_max_dist': 2.0, 'laser_min_range': -1.0,
        'laser_max_range': 100.0}
SUPPORT_RADIUS_M = 0.5
SUPPORT_YAW_DEG = 20.0


def wrap(a):
    return np.arctan2(np.sin(a), np.cos(a))


def support_mask(particles, candidate, radius=SUPPORT_RADIUS_M, yaw_deg=SUPPORT_YAW_DEG):
    """Joint XY and heading support, identical to the competing-pose report."""
    p = np.asarray(particles, dtype=float)
    if p.ndim != 2 or p.shape[1] < 3 or not np.all(np.isfinite(p[:, :3])):
        raise ValueError('finite N x 3 particle poses required')
    c = np.asarray(candidate, dtype=float)
    return ((np.hypot(p[:, 0] - c[0], p[:, 1] - c[1]) <= radius) &
            (np.abs(wrap(p[:, 2] - c[2])) <= math.radians(yaw_deg)))


def distance_field(occupied, resolution, max_dist):
    """Distance to the nearest occupied cell, capped like map_update_cspace."""
    from scipy.ndimage import distance_transform_edt
    occupied = np.asarray(occupied, dtype=bool)
    if not occupied.any():
        raise ValueError('map contains no occupied cells')
    return np.minimum(distance_transform_edt(~occupied) * resolution, max_dist)


def beam_indices(range_count, max_beams):
    step = (range_count - 1) // (max_beams - 1) if max_beams > 1 else 1
    return np.arange(0, range_count, max(1, step))


def likelihood_field(particles, scan, laser_in_base, field, origin_xy, resolution, params=AMCL):
    """nav2_amcl 1.1.20 likelihood-field weight factor for each particle.

    ``scan`` = (angle_min, angle_increment, ranges, range_min, range_max).
    Returns p = 1 + sum(pz^3); AMCL multiplies each particle weight by p.
    """
    angle_min, increment, ranges, range_min, range_max = scan
    ranges = np.asarray(ranges, dtype=float)
    if params['laser_max_range'] > 0:
        range_max = min(range_max, params['laser_max_range'])
    if params['laser_min_range'] > 0:
        range_min = max(range_min, params['laser_min_range'])
    idx = beam_indices(len(ranges), params['max_beams'])
    r = ranges[idx].copy()
    r[r <= range_min] = range_max          # amcl_node maps short ranges to max
    keep = ~np.isnan(r) & (r < range_max)  # max-range readings are skipped
    idx, r = idx[keep], r[keep]
    bearing = angle_min + idx * increment
    p = np.asarray(particles, dtype=float)[:, :3]
    x, y, th = p[:, 0:1], p[:, 1:2], p[:, 2:3]
    c, s = np.cos(th), np.sin(th)
    lx = x + c * laser_in_base[0] - s * laser_in_base[1]
    ly = y + s * laser_in_base[0] + c * laser_in_base[1]
    lt = th + laser_in_base[2]
    hx = lx + r * np.cos(lt + bearing)
    hy = ly + r * np.sin(lt + bearing)
    # MAP_GXWX / MAP_GYWY with nav2's centred map origin reduce to this.
    i = np.floor((hx - origin_xy[0]) / resolution + 0.5).astype(int)
    j = np.floor((hy - origin_xy[1]) / resolution + 0.5).astype(int)
    height, width = field.shape
    valid = (i >= 0) & (i < width) & (j >= 0) & (j < height)
    z = np.full(i.shape, float(params['laser_likelihood_max_dist']))
    z[valid] = field[j[valid], i[valid]]
    pz = (params['z_hit'] * np.exp(-z * z / (2 * params['sigma_hit'] ** 2)) +
          params['z_rand'] / range_max)
    return 1.0 + np.sum(pz ** 3, axis=1)


def resample_survival(weights, sizes, members, trials, seed, track_index=None):
    """Multinomial resampling of frozen poses with prescribed sample counts.

    ``weights`` is updates x particles (likelihood of each ORIGINAL particle on
    that update's scan). Returns member counts and tracked-index copies at end.
    """
    weights = np.asarray(weights, dtype=float)
    members = np.asarray(members, dtype=bool)
    if weights.ndim != 2 or weights.shape[0] != len(sizes) or weights.shape[1] != len(members):
        raise ValueError('weights must be updates x particles matching sizes/members')
    if np.any(~np.isfinite(weights)) or np.any(weights <= 0):
        raise ValueError('finite positive weights required')
    rng = np.random.default_rng(seed)
    member_end = np.empty(trials, dtype=int)
    tracked_end = np.zeros(trials, dtype=int)
    for t in range(trials):
        idx = np.arange(weights.shape[1])
        for update, n in enumerate(sizes):
            w = weights[update][idx]
            idx = idx[rng.choice(len(idx), size=int(n), p=w / w.sum())]
        member_end[t] = int(members[idx].sum())
        if track_index is not None:
            tracked_end[t] = int((idx == track_index).sum())
    return member_end, tracked_end


def _reader(db_path):
    """Return a decode(raw, type_name) function: rclpy on Jetson, rosbags elsewhere."""
    try:
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message
        return lambda raw, typ: deserialize_message(raw, get_message(typ))
    except ImportError:
        from rosbags.typesys import Stores, get_typestore, get_types_from_msg
        store = get_typestore(Stores.ROS2_HUMBLE)
        store.register(get_types_from_msg('geometry_msgs/Pose pose\nfloat64 weight', 'nav2_msgs/msg/Particle'))
        store.register(get_types_from_msg('std_msgs/Header header\nnav2_msgs/Particle[] particles',
                                          'nav2_msgs/msg/ParticleCloud'))
        return store.deserialize_cdr


def _yaw(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


def _pose(p):
    return (p.position.x, p.position.y, _yaw(p.orientation))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bag')
    parser.add_argument('output')
    parser.add_argument('--trials', type=int, default=4000)
    parser.add_argument('--seed', type=int, default=20261010)
    args = parser.parse_args()
    if Path(args.bag).name != BAG_NAME:
        raise ValueError('locked hypotheses and offsets belong only to ' + BAG_NAME)
    segments = list(Path(args.bag).glob('*.db3'))
    if len(segments) != 1:
        raise ValueError('requires one SQLite segment')
    db = sqlite3.connect('file:' + str(segments[0]) + '?mode=ro', uri=True)
    decode = _reader(segments[0])
    start = db.execute('SELECT MIN(timestamp) FROM messages').fetchone()[0] / 1e9
    topics = {n: (i, t) for i, n, t in db.execute('SELECT id,name,type FROM topics')}

    def rows(name):
        ident, typ = topics[name]
        for received, raw in db.execute(
                'SELECT timestamp,data FROM messages WHERE topic_id=? ORDER BY timestamp', (ident,)):
            yield received / 1e9 - start, decode(raw, typ)

    maps = list(rows('/map'))
    if len(maps) != 1:
        raise ValueError('expected exactly one recorded map')
    grid_msg = maps[0][1]
    info = grid_msg.info
    grid = np.asarray(grid_msg.data, dtype=np.int16).reshape(info.height, info.width)
    if abs(_pose(info.origin)[2]) > 1e-9:
        raise ValueError('rotated map origin not supported by nav2_amcl map conversion')
    field = distance_field(grid == 100, info.resolution, AMCL['laser_likelihood_max_dist'])
    origin_xy = (info.origin.position.x, info.origin.position.y)
    static = {}
    for _, msg in rows('/tf_static'):
        for tr in msg.transforms:
            q = tr.transform.rotation
            static[(tr.header.frame_id.strip('/'), tr.child_frame_id.strip('/'))] = np.array(
                (tr.transform.translation.x, tr.transform.translation.y, _yaw(q)))
    base = static.get(('base_link', 'base_footprint'))
    if base is None or np.linalg.norm(base) > 1e-8:
        raise ValueError('explicit identity base transform required')
    laser = static[('base_footprint', 'laser_frame')]
    clouds = [(t, np.array([[*_pose(p.pose), p.weight] for p in m.particles]))
              for t, m in rows('/particle_cloud')]
    scans = [(t, (m.angle_min, m.angle_increment, np.asarray(m.ranges, dtype=float),
                  m.range_min, m.range_max)) for t, m in rows('/scan')]
    scan_times = np.array([s[0] for s in scans])
    odom = [(t, np.array(_pose(m.pose.pose))) for t, m in rows('/odom')]
    odom_times = np.array([o[0] for o in odom])
    amcl = [(t, np.array(_pose(m.pose.pose))) for t, m in rows('/amcl_pose')]

    def scan_before(t):
        i = int(np.searchsorted(scan_times, t, side='right')) - 1
        if i < 0:
            raise ValueError('no scan before update')
        return scans[i]

    def odom_at(t):
        i = int(np.clip(np.searchsorted(odom_times, t), 0, len(odom) - 1))
        return odom[i][1]

    # Cloud immediately before the +352.107 s training scan (+351.997 s).
    start_index = max(k for k, (t, _) in enumerate(clouds) if t <= 352.107)
    room, false_ref, anchor = (np.array(p) for p in (REFINED_ROOM, REFINED_FALSE, LATE_FALSE_ANCHOR))
    trace = []
    for k in range(start_index - 25, min(len(clouds) - 1, start_index + 30)):
        t, P = clouds[k]
        used = scan_before(clouds[k + 1][0])
        w = likelihood_field(P, used[1], laser, field, origin_xy, info.resolution)
        exact = likelihood_field(np.array([room, anchor]), used[1], laser, field, origin_xy, info.resolution)
        mask = support_mask(P, room)
        prev = odom_at(clouds[k - 1][0])
        now = odom_at(t)
        trace.append({
            'cloud_index': k, 'receipt_offset_s': round(t, 3), 'particles': len(P),
            'unique_at_1e_minus_6': int(len(np.unique(np.round(P[:, :3], 6), axis=0))),
            'published_weights_uniform': bool(np.ptp(P[:, 3]) < 1e-12),
            'odometry_step_since_previous_cloud_m': round(float(np.hypot(*(now[:2] - prev[:2]))), 4),
            'odometry_step_since_previous_cloud_deg': round(math.degrees(abs(float(wrap(now[2] - prev[2])))), 3),
            'room_support_count': int(mask.sum()),
            'room_support_weight_fraction': float(P[mask, 3].sum() / P[:, 3].sum()),
            'late_false_anchor_support_count': int(support_mask(P, anchor).sum()),
            'refined_false_support_count': int(support_mask(P, false_ref).sum()),
            'next_update_scan_offset_s': round(used[0], 3),
            'next_update_likelihood': {
                'cloud_mean': float(w.mean()), 'cloud_max': float(w.max()),
                'room_support_mean': float(w[mask].mean()) if mask.any() else None,
                'room_support_relative_to_cloud_mean': float(w[mask].mean() / w.mean()) if mask.any() else None,
                'exact_refined_room_pose': float(exact[0]),
                'exact_late_false_anchor': float(exact[1]),
            }})
    extinct = next(r for r in trace if r['cloud_index'] > start_index and r['room_support_count'] == 0)
    end_index = extinct['cloud_index']
    P0 = clouds[start_index][1][:, :3]
    sizes = [len(clouds[k][1]) for k in range(start_index + 1, end_index + 1)]
    # Below AMCL's update_min_d/update_min_a (0.05 m / 0.05 rad), AMCL applies
    # no motion update; only forced no-motion updates can occur.
    first, last = odom_at(clouds[start_index][0]), odom_at(clouds[end_index][0])
    odom_total_m = float(np.hypot(*(last[:2] - first[:2])))
    odom_total_rad = abs(float(wrap(last[2] - first[2])))
    stationary = odom_total_m < 0.05 and odom_total_rad < 0.05
    members = support_mask(P0, room)
    W = np.array([likelihood_field(P0, scan_before(clouds[k + 1][0])[1], laser, field, origin_xy,
                                   info.resolution) for k in range(start_index, end_index)])
    neutral_end, _ = resample_survival(np.ones_like(W), sizes, members, args.trials, args.seed)
    model_end, _ = resample_survival(W, sizes, members, args.trials, args.seed + 1)
    Pp = np.vstack([P0, room])
    Wp = np.array([likelihood_field(Pp, scan_before(clouds[k + 1][0])[1], laser, field, origin_xy,
                                    info.resolution) for k in range(start_index, end_index)])
    _, peak_end = resample_survival(Wp, sizes, np.r_[members, True], args.trials, args.seed + 2,
                                    track_index=len(Pp) - 1)
    offsets = np.array([np.hypot(*(q[:2] - room[:2])) for q in P0[members]])
    headings = np.array([math.degrees(abs(float(wrap(q[2] - room[2])))) for q in P0[members]])
    sensitivity = {f'{dx:.2f}m_{dyaw}deg': float(likelihood_field(
        (room + [dx, 0, math.radians(dyaw)])[None], scan_before(clouds[start_index + 1][0])[1],
        laser, field, origin_xy, info.resolution)[0])
        for dx in (0, .05, .1, .15, .2, .3) for dyaw in (0, 5, 12)}
    result = {
        'source_bag': BAG_NAME, 'navigation_authorized': False,
        'amcl_parameters': AMCL, 'room_candidate': list(REFINED_ROOM),
        'start_cloud': {'index': start_index, 'receipt_offset_s': round(clouds[start_index][0], 3),
                        'room_support_count': int(members.sum()),
                        'room_support_xy_offset_m': [round(float(v), 3) for v in sorted(offsets)],
                        'room_support_heading_offset_deg': [round(float(v), 1) for v in sorted(headings)]},
        'extinction_cloud': {'index': end_index, 'receipt_offset_s': extinct['receipt_offset_s'],
                             'updates_after_start': len(sizes), 'kld_sample_counts': sizes,
                             'odometry_total_change_m': round(odom_total_m, 5),
                             'odometry_total_change_deg': round(math.degrees(odom_total_rad), 4),
                             'below_amcl_motion_update_thresholds': stationary},
        'room_peak_sensitivity_likelihood': sensitivity,
        'resampling_experiment': {
            'trials': args.trials, 'seed': args.seed, 'sampler': 'multinomial, frozen poses, observed KLD counts',
            'neutral_equal_weights': {'p_extinct': float(np.mean(neutral_end == 0)),
                                      'median_remaining': float(np.median(neutral_end))},
            'likelihood_field_weights': {'p_extinct': float(np.mean(model_end == 0)),
                                         'median_remaining': float(np.median(model_end))},
            'room_support_mean_relative_weight_per_update': [
                round(float(v), 3) for v in W[:, members].mean(axis=1) / W.mean(axis=1)],
            'counterfactual_one_particle_at_refined_room_pose': {
                'relative_weight_per_update': [round(float(v), 3) for v in Wp[:, -1] / Wp[:, :-1].mean(axis=1)],
                'p_survives': float(np.mean(peak_end > 0)),
                'median_copies': float(np.median(peak_end)),
                'final_particles': sizes[-1]},
            'observed_room_support_at_end': 0},
        'amcl_pose_after_extinction': [round(float(v), 4) for v in
                                       [a for a in amcl if a[0] <= extinct['receipt_offset_s'] + 1][-1][1]],
        'trace': trace,
        'limitations': [
            'Published clouds hold post-resample uniform weights; per-particle likelihoods are recomputed, not AMCL internal values',
            'Scan-to-update pairing assumes each cloud follows the latest /scan received before it',
            'Room candidate is a retrospective scan fit from this same bag, not surveyed ground truth',
            'Resampling experiment freezes poses and imposes observed KLD counts; it is not an AMCL replay',
            'One recording only; no candidate fix was evaluated and no runtime change is implied'],
    }
    Path(args.output).write_text(json.dumps(result, indent=2, allow_nan=False))
    print(json.dumps({'output': args.output, 'navigation_authorized': False}))


if __name__ == '__main__':
    main()
