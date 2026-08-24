#!/usr/bin/env python3
"""Repeatable one-motor forward/reverse encoder stress test for lifted ATLAS."""

import argparse
import statistics
import time

from Rosmaster_Lib import Rosmaster


FORWARD_PWM = {1: 60, 2: -60, 3: -60, 4: 60}


def delta(after, before):
    return tuple(int(after[index]) - int(before[index]) for index in range(4))


def command(bot, motor, pwm, run_s, rest_s):
    before = bot.get_motor_encoder()
    outputs = [0, 0, 0, 0]
    outputs[motor - 1] = pwm
    bot.set_motor(*outputs)
    time.sleep(run_s)
    bot.set_motor(0, 0, 0, 0)
    time.sleep(rest_s)
    after = bot.get_motor_encoder()
    return delta(after, before)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("motor", type=int, choices=(1, 2, 3, 4))
    parser.add_argument("--cycles", type=int, default=5)
    parser.add_argument("--run", type=float, default=1.5)
    parser.add_argument("--rest", type=float, default=0.8)
    args = parser.parse_args()
    if not 2 <= args.cycles <= 10:
        raise SystemExit("cycles must be 2..10")
    if not 0.5 <= args.run <= 3.0 or not 0.5 <= args.rest <= 3.0:
        raise SystemExit("unsafe run/rest duration")

    bot = Rosmaster(car_type=5, com="/dev/yahboom")
    bot.create_receive_threading()
    bot.set_car_type(5)
    bot.set_auto_report_state(True, False)
    time.sleep(1.5)
    motor = args.motor
    forward_pwm = FORWARD_PWM[motor]
    target = motor - 1
    forward_counts = []
    reverse_counts = []
    cross_max = 0
    voltage_start = float(bot.get_battery_voltage())
    try:
        bot.set_motor(0, 0, 0, 0)
        time.sleep(0.5)
        for cycle in range(1, args.cycles + 1):
            fwd = command(bot, motor, forward_pwm, args.run, args.rest)
            rev = command(bot, motor, -forward_pwm, args.run, args.rest)
            forward_counts.append(fwd[target])
            reverse_counts.append(rev[target])
            cross_max = max(
                cross_max,
                *(abs(value) for index, value in enumerate(fwd) if index != target),
                *(abs(value) for index, value in enumerate(rev) if index != target),
            )
            print(f"cycle={cycle} forward={fwd} reverse={rev}", flush=True)
    finally:
        bot.set_motor(0, 0, 0, 0)

    expected_forward_sign = 1 if forward_pwm > 0 else -1
    sign_ok = all(value * expected_forward_sign > 0 for value in forward_counts)
    sign_ok = sign_ok and all(value * expected_forward_sign < 0 for value in reverse_counts)
    magnitudes = [abs(value) for value in forward_counts + reverse_counts]
    mean_counts = statistics.mean(magnitudes)
    cv = statistics.pstdev(magnitudes) / mean_counts if mean_counts else float("inf")
    voltage_end = float(bot.get_battery_voltage())
    passed = sign_ok and mean_counts >= 100.0 and cv <= 0.35 and cross_max <= 25
    print(
        f"SUMMARY motor=M{motor} pass={passed} sign_ok={sign_ok} "
        f"mean_abs_counts={mean_counts:.1f} cv={cv:.3f} cross_max={cross_max} "
        f"battery_start={voltage_start:.1f}V battery_end={voltage_end:.1f}V",
        flush=True,
    )
    print("SAFETY STOP: ALL MOTOR OUTPUTS ZERO", flush=True)
    raise SystemExit(0 if passed else 2)


if __name__ == "__main__":
    main()
