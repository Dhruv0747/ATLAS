#!/usr/bin/env python3
"""Command one ATLAS steering servo with all traction motors held at zero."""

import argparse
import time

from Rosmaster_Lib import Rosmaster


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("axle", choices=("front", "rear"))
    parser.add_argument("angle", type=int)
    parser.add_argument("--front-hold", type=int, default=83)
    parser.add_argument("--rear-hold", type=int, default=106)
    args = parser.parse_args()

    angle = max(0, min(180, args.angle))
    front = angle if args.axle == "front" else args.front_hold
    rear = angle if args.axle == "rear" else args.rear_hold

    bot = Rosmaster(car_type=5, com="/dev/yahboom")
    bot.create_receive_threading()
    bot.set_car_type(5)
    bot.set_motor(0, 0, 0, 0)
    bot.set_pwm_servo(1, front)
    bot.set_pwm_servo(2, rear)
    time.sleep(1.0)
    bot.set_motor(0, 0, 0, 0)
    print(f"front={front} rear={rear} traction_motors=0", flush=True)


if __name__ == "__main__":
    main()
