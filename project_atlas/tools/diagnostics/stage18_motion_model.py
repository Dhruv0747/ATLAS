"""Isolated 4WS model and evidence gate. Never imported by the live driver.

Angles MUST be measured virtual axle road angles, not PWM/servo commands.
Body reference is the midpoint between axles; dx is signed longitudinal travel.
"""
import math


def geometry(front_rad, rear_rad, wheelbase, track):
    values = (front_rad, rear_rad, wheelbase, track)
    if not all(math.isfinite(v) for v in values) or wheelbase <= 0 or track <= 0:
        raise ValueError('finite angles and positive dimensions required')
    if max(abs(front_rad), abs(rear_rad)) >= math.radians(75):
        raise ValueError('outside validated mathematical small-wheel-angle envelope')
    f, r = math.tan(front_rad), math.tan(rear_rad)
    k, lateral = (f-r)/wheelbase, (f+r)/2
    positions = ((-wheelbase/2, track/2), (-wheelbase/2, -track/2),
                 (wheelbase/2, track/2), (wheelbase/2, -track/2))
    return {'curvature': k, 'lateral_ratio': lateral,
            'scales': tuple(math.hypot(1-k*y, lateral+k*x) for x, y in positions),
            'wheel_angles': tuple(math.atan2(lateral+k*x, 1-k*y) for x, y in positions)}


def integrate(x, y, yaw, dx, lateral_ratio, dyaw):
    """Exact constant-body-twist SE(2) increment; no reset/map-frame operation."""
    if not all(math.isfinite(v) for v in (x, y, yaw, dx, lateral_ratio, dyaw)):
        raise ValueError('finite motion required')
    a = math.sin(dyaw)/dyaw if abs(dyaw) > 1e-8 else 1-dyaw*dyaw/6
    b = (1-math.cos(dyaw))/dyaw if abs(dyaw) > 1e-8 else dyaw/2
    dy = dx*lateral_ratio
    bx, by = a*dx-b*dy, b*dx+a*dy
    return x+math.cos(yaw)*bx-math.sin(yaw)*by, y+math.sin(yaw)*bx+math.cos(yaw)*by, yaw+dyaw


def consistency(wheel_yaw, gyro_yaw, lidar_yaw, *, gyro_coverage, lidar_valid,
                gyro_uncertainty, lidar_uncertainty, sync_uncertainty,
                max_rate, wheel_uncertainty):
    """Interval evidence, not a calibrated probability or control authority.

    Missing references are UNKNOWN, never healthy. User-supplied uncertainties
    must include mounting, scale/bias and ICP systematic errors.
    """
    values = (wheel_yaw, gyro_yaw, lidar_yaw, gyro_uncertainty,
              lidar_uncertainty, sync_uncertainty, max_rate, wheel_uncertainty)
    if (any(v is None or not math.isfinite(v) for v in values) or
            min(gyro_uncertainty, lidar_uncertainty, sync_uncertainty, max_rate, wheel_uncertainty) < 0 or
            not math.isfinite(gyro_coverage) or gyro_coverage < .9 or not lidar_valid):
        return {'classification': 'UNKNOWN', 'authority': 'NONE'}
    timing = 2*sync_uncertainty*max_rate
    agreement_bound = gyro_uncertainty+lidar_uncertainty+timing
    if abs(gyro_yaw-lidar_yaw) > agreement_bound:
        state = 'REFERENCES_DISAGREE'
    elif (abs(wheel_yaw-gyro_yaw) > wheel_uncertainty+gyro_uncertainty+timing and
          abs(wheel_yaw-lidar_yaw) > wheel_uncertainty+lidar_uncertainty+timing):
        state = 'WHEEL_SUSPECT'
    else:
        state = 'CONSISTENT_WITH_ASSUMED_BOUNDS'
    return {'classification': state, 'authority': 'NONE',
            'reference_agreement_bound_rad': agreement_bound, 'timing_bound_rad': timing}
