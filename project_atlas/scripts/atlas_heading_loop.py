"""Closed-loop yaw rate for autonomous driving (2026-11-15, owner: "self adjustment — when weight is unbalanced or the
surface is a little tilted it should still balance"). Pure, no ROS.

Nav2 commands a yaw rate wz; the rover's real yaw rate is measured by the IM10A gyro (/im10a/imu/bias_corrected_candidate,
the same signal the EKF trusts). A weight imbalance or a side slope makes the rover yaw although wz = 0 (it drifted right
on 2026-11-15). This PI loop adds a bounded correction to the commanded wz so the measured yaw rate follows the command.
It only runs while the rover is actually rolling under an autonomous command; REMOTE driving is never touched. Stale
IMU data or a stopped rover clears the correction (fail-safe: falls back to the plain Nav2 command).
"""
import math

DEFAULTS = {
    'kp': 0.8,                    # rad/s of correction per rad/s of yaw-rate error
    'ki': 1.2,                    # integral gain (1/s): learns a constant drift such as a weight imbalance
    'max_correction': 0.35,       # rad/s, |correction| bound (~10 deg steering at 0.15 m/s on this wheelbase)
    'min_speed_mps': 0.04,        # below this the gyro error is dominated by noise / no steering authority
    'imu_max_age_s': 0.3,
    'error_deadband': 0.01,       # rad/s
}


class HeadingLoop:
    def __init__(self, params=None):
        p = dict(DEFAULTS)
        p.update(params or {})
        for k, v in p.items():
            if not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
                raise ValueError(f'heading loop parameter {k}={v!r} must be finite and >= 0')
        self.p = p
        self.reset()

    def reset(self):
        self.integrator = 0.0
        self.last_correction = 0.0
        self.last_reason = 'idle'

    def update(self, wz_cmd, wz_meas, speed_mps, dt_s, imu_age_s):
        """Returns the corrected wz. wz_cmd/wz_meas in rad/s (CCW +), speed_mps = measured |forward speed|."""
        p = self.p
        vals = (wz_cmd, speed_mps, dt_s)
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in vals) or dt_s <= 0 or dt_s > 0.5:
            self.reset(); self.last_reason = 'invalid input'
            return wz_cmd if isinstance(wz_cmd, (int, float)) and math.isfinite(wz_cmd) else 0.0
        if (wz_meas is None or not math.isfinite(wz_meas) or imu_age_s is None or not math.isfinite(imu_age_s)
                or not 0 <= imu_age_s <= p['imu_max_age_s']):
            self.reset(); self.last_reason = 'imu stale'
            return wz_cmd
        if abs(speed_mps) < p['min_speed_mps']:
            # keep the learned drift (integrator) across short stops, but apply nothing while not rolling
            self.last_correction = 0.0; self.last_reason = 'not rolling'
            return wz_cmd
        err = wz_cmd - wz_meas
        if abs(err) < p['error_deadband']:
            err = 0.0
        self.integrator += p['ki'] * err * dt_s
        m = p['max_correction']
        self.integrator = max(-m, min(m, self.integrator))
        corr = max(-m, min(m, p['kp'] * err + self.integrator))
        self.last_correction = corr
        self.last_reason = 'tracking'
        return wz_cmd + corr
