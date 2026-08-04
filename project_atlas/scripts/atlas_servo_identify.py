#!/usr/bin/env python3
import argparse
import sys
import time


def yahboom_move(port, angle):
    sys.path.insert(0, "/home/jetson/project_atlas/scripts")
    from Rosmaster_Lib import Rosmaster

    bot = Rosmaster(car_type=5, com="/dev/yahboom")
    bot.create_receive_threading()
    time.sleep(0.4)
    bot.set_pwm_servo(int(port), int(angle))
    time.sleep(0.5)


class Pca9685:
    def __init__(self, address=0x40, bus=1):
        import smbus2

        self.address = address
        self.bus = smbus2.SMBus(bus)
        self.bus.write_byte_data(address, 0x00, 0x10)
        time.sleep(0.005)
        prescale = round(25000000 / (4096 * 50)) - 1
        self.bus.write_byte_data(address, 0xFE, prescale)
        self.bus.write_byte_data(address, 0x00, 0x00)
        time.sleep(0.005)
        self.bus.write_byte_data(address, 0x00, 0xA0)

    def pulse(self, channel, pulse_us):
        pulse_us = max(500, min(2500, int(pulse_us)))
        ticks = int(pulse_us * 4096 / 20000)
        self.bus.write_i2c_block_data(
            self.address,
            0x06 + 4 * int(channel),
            [0x00, 0x00, ticks & 0xFF, ticks >> 8],
        )


def pca_move(channel, pulse_us):
    pca = Pca9685()
    pca.pulse(channel, pulse_us)
    time.sleep(0.4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["yahboom", "pca"], required=True)
    ap.add_argument("--channel", type=int, required=True)
    ap.add_argument("--center", type=int, default=None)
    ap.add_argument("--delta", type=int, default=8)
    args = ap.parse_args()

    if args.kind == "yahboom":
        center = 90 if args.center is None else args.center
        values = [center, center + args.delta, center - args.delta, center]
        for value in values:
            yahboom_move(args.channel, value)
            time.sleep(0.45)
        print(f"moved yahboom servo port {args.channel}: {values}")
    else:
        center = 1500 if args.center is None else args.center
        values = [center, center + args.delta * 10, center - args.delta * 10, center]
        for value in values:
            pca_move(args.channel, value)
            time.sleep(0.45)
        print(f"moved pca channel {args.channel}: {values} us")


if __name__ == "__main__":
    main()
