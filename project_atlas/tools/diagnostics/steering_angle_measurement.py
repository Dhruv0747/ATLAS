#!/usr/bin/env python3
"""Offline, perspective-corrected road-wheel angle and observability harness.

Input is manually picked image points on a measured coplanar reference grid.
It supplies visual estimates with stated uncertainty, never physical feedback
to ROS. Plane coordinates are +X rover-forward and +Y rover-left.
"""
import argparse
import json
import math


def solve(matrix, rhs):
    n = len(rhs)
    a = [list(map(float, row)) + [float(value)] for row, value in zip(matrix, rhs)]
    if len(a) != n or any(len(row) != n + 1 for row in a):
        raise ValueError('square system required')
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-10:
            raise ValueError('measurement geometry is unobservable or degenerate')
        a[col], a[pivot] = a[pivot], a[col]
        divisor = a[col][col]
        a[col] = [v / divisor for v in a[col]]
        for row in range(n):
            if row == col:
                continue
            factor = a[row][col]
            a[row] = [v - factor * p for v, p in zip(a[row], a[col])]
    return [row[-1] for row in a]


def homography(reference):
    if len(reference) != 4:
        raise ValueError('four measured coplanar reference points required')
    matrix, rhs = [], []
    for item in reference:
        x, y = item['image_xy']
        u, v = item['plane_xy_m']
        if not all(math.isfinite(float(z)) for z in (x, y, u, v)):
            raise ValueError('finite reference coordinates required')
        matrix.extend(([x, y, 1, 0, 0, 0, -u*x, -u*y],
                       [0, 0, 0, x, y, 1, -v*x, -v*y]))
        rhs.extend((u, v))
    return solve(matrix, rhs) + [1.0]


def transform(point, h):
    if len(point) != 2 or not all(math.isfinite(float(z)) for z in point):
        raise ValueError('finite two-dimensional image point required')
    x, y = point
    denominator = h[6]*x + h[7]*y + h[8]
    if abs(denominator) < 1e-10:
        raise ValueError('point projects to infinity')
    return ((h[0]*x + h[1]*y + h[2]) / denominator,
            (h[3]*x + h[4]*y + h[5]) / denominator)


def road_angle(reference, chassis_axis, wheel_axis):
    if len(chassis_axis) != 2 or len(wheel_axis) != 2:
        raise ValueError('two directed points per axis required')
    h = homography(reference)
    def vector(axis):
        a, b = [transform(point, h) for point in axis]
        v = b[0] - a[0], b[1] - a[1]
        if math.hypot(*v) < 0.02:
            raise ValueError('axis reference shorter than 2 cm')
        return v
    cx, cy = vector(chassis_axis)
    wx, wy = vector(wheel_axis)
    return math.degrees(math.atan2(cx*wy - cy*wx, cx*wx + cy*wy))


def visual_measurement(reference, chassis_axis, wheel_axis, pixel_error=2.0):
    if not 0 < pixel_error <= 10:
        raise ValueError('state point-picking error in pixels (0..10)')
    # First-order worst-case point-picking bound, not total physical accuracy.
    points = [list(r['image_xy']) for r in reference] + [list(p) for p in chassis_axis + wheel_axis]
    base = road_angle(reference, chassis_axis, wheel_axis)
    uncertainty = 0.0
    for i in range(len(points)):
        for dimension in (0, 1):
            changes = []
            for sign in (-1, 1):
                perturbed = [p.copy() for p in points]
                perturbed[i][dimension] += sign * pixel_error
                ref = [dict(r, image_xy=perturbed[j]) for j, r in enumerate(reference)]
                estimate = road_angle(ref, perturbed[4:6], perturbed[6:8])
                changes.append(abs((estimate - base + 180) % 360 - 180))
            uncertainty += max(changes)
    return {'road_wheel_angle_deg': round(base, 3),
            'point_picking_bound_deg': round(uncertainty, 3),
            'usable_for_mapping': uncertainty <= 3.0,
            'method': 'visual estimate; perspective rectified; no ROS authority',
            'unmeasured_errors': ['reference placement', 'non-coplanarity', 'tyre deformation']}


def video_ros_time(video_pts_s, anchors):
    if len(anchors) != 2:
        raise ValueError('independent visible sync markers before and after required')
    first, last = sorted(anchors, key=lambda a: a['video_pts_s'])
    interval = last['video_pts_s'] - first['video_pts_s']
    if interval < 5 or not first['video_pts_s'] <= video_pts_s <= last['video_pts_s']:
        raise ValueError('sync anchors must bracket the sample and span at least 5 seconds')
    ratio = (last['ros_time_ns'] - first['ros_time_ns']) * 1e-9 / interval
    if not 0.99 <= ratio <= 1.01:
        raise ValueError('video/ROS clocks inconsistent; check sync and NTP steps')
    stamp = first['ros_time_ns'] + int((video_pts_s - first['video_pts_s']) * ratio * 1e9)
    uncertainty = max(float(a['uncertainty_s']) for a in anchors)
    if not math.isfinite(uncertainty) or not 0 < uncertainty <= 1:
        raise ValueError('explicit finite sync uncertainty required')
    return stamp, uncertainty


def rolling_delta(angles_deg, wheel_deltas_m, positions_m, gyro_delta_rad=None):
    """Isolated least-squares wheel rolling model using MEASURED road angles.

    Two encoders alone cannot observe all three body-motion components. With
    independently measured yaw, two nonparallel wheel directions can observe
    translation. Degenerate pairs explicitly fail; this grants no authority.
    """
    if not (len(angles_deg) == len(wheel_deltas_m) == len(positions_m)) or not angles_deg:
        raise ValueError('matching nonempty wheel measurements required')
    rows, rhs = [], []
    for angle, distance, (x, y) in zip(angles_deg, wheel_deltas_m, positions_m):
        if not all(math.isfinite(float(z)) for z in (angle, distance, x, y)):
            raise ValueError('finite measurements required')
        c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        rotation = -y*c + x*s
        if gyro_delta_rad is None:
            rows.append([c, s, rotation]); rhs.append(distance)
        else:
            if not math.isfinite(gyro_delta_rad):
                raise ValueError('finite independent yaw required')
            rows.append([c, s]); rhs.append(distance - rotation*gyro_delta_rad)
    n = len(rows[0])
    normal = [[sum(row[i]*row[j] for row in rows) for j in range(n)] for i in range(n)]
    projected = [sum(row[i]*value for row, value in zip(rows, rhs)) for i in range(n)]
    try:
        result = solve(normal, projected)
    except ValueError:
        return {'observable': False, 'encoder_count': len(rows), 'authority': 'NONE',
                'reason': 'wheel directions do not independently constrain body motion'}
    dx, dy = result[:2]
    yaw = result[2] if gyro_delta_rad is None else gyro_delta_rad
    residuals = [sum(a*b for a, b in zip(row, result)) - value for row, value in zip(rows, rhs)]
    lateral = []
    for angle, (x, y) in zip(angles_deg, positions_m):
        c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        lateral.append(-s*(dx-yaw*y) + c*(dy+yaw*x))
    return {'observable': True, 'dx_m': dx, 'dy_m': dy, 'dyaw_rad': yaw,
            'rolling_residuals_m': residuals, 'lateral_slip_residuals_m': lateral,
            'encoder_count': len(rows), 'gyro_required': gyro_delta_rad is not None,
            'authority': 'NONE', 'validation': 'offline estimate only'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('measurements', help='JSON with reference, axes, video PTS and two sync anchors')
    args = parser.parse_args()
    with open(args.measurements, encoding='utf-8') as handle:
        data = json.load(handle)
    result = []
    for sample in data['samples']:
        stamp, uncertainty = video_ros_time(sample['video_pts_s'], data['sync_anchors'])
        reference = sample.get('plane_reference', data.get('plane_reference'))
        if reference is None:
            raise ValueError('each camera pose needs its own reference points')
        wheels = {name: visual_measurement(reference, sample['chassis_forward_image'], axis,
                                          data['point_picking_error_px'])
                  for name, axis in sample['wheel_forward_axes_image'].items()}
        result.append({'ros_time_ns': stamp, 'sync_uncertainty_s': uncertainty,
                       'video_pts_s': sample['video_pts_s'], 'wheels': wheels})
    print(json.dumps({'samples': result, 'authority': 'NONE'}, indent=2))


if __name__ == '__main__':
    main()
