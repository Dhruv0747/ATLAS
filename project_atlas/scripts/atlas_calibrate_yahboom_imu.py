#!/usr/bin/env python3
"""Stationary calibration for the Yahboom motor-controller IMU.

The Yahboom base service must be stopped while this tool owns its serial port.
The tool never commands motion and repeatedly writes zero motor PWM. It emits
YAML that can be reviewed before updating yahboom_imu_calibration.yaml.
"""
import argparse
import math
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from Rosmaster_Lib import Rosmaster


def circular_mean_degrees(values):
    sin_mean = statistics.fmean(math.sin(math.radians(v)) for v in values)
    cos_mean = statistics.fmean(math.cos(math.radians(v)) for v in values)
    return math.degrees(math.atan2(sin_mean, cos_mean)) % 360.0


def angle_delta_degrees(value, reference):
    return (float(value) - float(reference) + 180.0) % 360.0 - 180.0


def summary(values):
    return statistics.fmean(values), statistics.pstdev(values)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', default='/dev/yahboom')
    parser.add_argument('--duration', type=float, default=30.0)
    parser.add_argument('--warmup', type=float, default=2.0)
    args = parser.parse_args()
    if args.duration < 10.0:
        parser.error('--duration must be at least 10 seconds')

    bot = Rosmaster(car_type=5, com=args.port)
    bot.create_receive_threading()
    bot.set_auto_report_state(True, False)
    bot.set_motor(0, 0, 0, 0)
    time.sleep(args.warmup)

    fields = {name: [] for name in (
        'roll', 'pitch', 'heading', 'gx', 'gy', 'gz',
        'ax', 'ay', 'az', 'mx', 'my', 'mz'
    )}
    first_encoders = tuple(bot.get_motor_encoder())
    deadline = time.monotonic() + args.duration
    try:
        while time.monotonic() < deadline:
            # Reassert zero PWM throughout calibration. This tool never moves
            # the rover, even if an old controller command was latched.
            bot.set_motor(0, 0, 0, 0)
            roll, pitch, heading = bot.get_imu_attitude_data(True)
            gx, gy, gz = bot.get_gyroscope_data()
            ax, ay, az = bot.get_accelerometer_data()
            mx, my, mz = bot.get_magnetometer_data()
            for key, value in {
                'roll': roll, 'pitch': pitch, 'heading': heading,
                'gx': gx, 'gy': gy, 'gz': gz,
                'ax': ax, 'ay': ay, 'az': az,
                'mx': mx, 'my': my, 'mz': mz,
            }.items():
                fields[key].append(float(value))
            time.sleep(0.05)
    finally:
        bot.set_motor(0, 0, 0, 0)

    final_encoders = tuple(bot.get_motor_encoder())
    encoder_delta = [final_encoders[i] - first_encoders[i] for i in range(4)]
    moved = any(abs(value) > 2 for value in encoder_delta)
    heading_mean = circular_mean_degrees(fields['heading'])
    heading_errors = [angle_delta_degrees(v, heading_mean) for v in fields['heading']]
    roll_mean, roll_std = summary(fields['roll'])
    pitch_mean, pitch_std = summary(fields['pitch'])
    gyro_means = [summary(fields[axis])[0] for axis in ('gx', 'gy', 'gz')]
    gyro_stds = [summary(fields[axis])[1] for axis in ('gx', 'gy', 'gz')]
    accel_means = [summary(fields[axis])[0] for axis in ('ax', 'ay', 'az')]
    accel_stds = [summary(fields[axis])[1] for axis in ('ax', 'ay', 'az')]
    gravity_target = 9.80665 if accel_means[2] >= 0.0 else -9.80665
    accel_bias = [accel_means[0], accel_means[1], accel_means[2] - gravity_target]

    print('yahboom_imu_calibration:')
    print('  source: yahboom_motor_controller')
    print('  method: stationary_raw_bias_and_attitude_zero')
    print(f'  duration_s: {args.duration:.3f}')
    print(f"  samples: {len(fields['roll'])}")
    print(f'  roll_zero_deg: {roll_mean:.8f}')
    print(f'  pitch_zero_deg: {pitch_mean:.8f}')
    print(f'  heading_zero_deg: {heading_mean:.8f}')
    print('  gyro_bias_rad_s: [' + ', '.join(f'{v:.9f}' for v in gyro_means) + ']')
    print('  accel_bias_m_s2: [' + ', '.join(f'{v:.9f}' for v in accel_bias) + ']')
    print(f'  stationary_roll_std_deg: {roll_std:.8f}')
    print(f'  stationary_pitch_std_deg: {pitch_std:.8f}')
    print(f'  stationary_heading_std_deg: {statistics.pstdev(heading_errors):.8f}')
    print(f'  stationary_heading_span_deg: {max(heading_errors) - min(heading_errors):.8f}')
    print('  gyro_std_rad_s: [' + ', '.join(f'{v:.9f}' for v in gyro_stds) + ']')
    print('  accel_std_m_s2: [' + ', '.join(f'{v:.9f}' for v in accel_stds) + ']')
    print('  encoder_delta: [' + ', '.join(str(v) for v in encoder_delta) + ']')
    print(f"  encoders_changed: {'true' if moved else 'false'}")
    print('  qualified_for_navigation: false')
    print('  qualification_note: stationary calibration only; dynamic yaw A/B test required')
    if moved:
        print('ERROR: encoder movement detected; discard this calibration', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
