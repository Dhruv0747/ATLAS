#!/usr/bin/env python3
import argparse
import time

import smbus2


class Pca9685:
    def __init__(self, address=0x42, bus_id=1):
        self.address = address
        self.bus = smbus2.SMBus(bus_id)
        self.write8(0x00, 0x10)
        time.sleep(0.005)
        prescale = round(25000000 / (4096 * 50)) - 1
        self.write8(0xFE, prescale)
        self.write8(0x00, 0x00)
        time.sleep(0.005)
        self.write8(0x00, 0xA0)

    def write8(self, reg, value):
        self.bus.write_byte_data(self.address, reg, value & 0xFF)

    def pulse(self, channel, pulse_us):
        pulse_us = max(700, min(2300, int(pulse_us)))
        ticks = int(pulse_us * 4096 / 20000)
        reg = 0x06 + 4 * int(channel)
        self.write8(reg, 0)
        self.write8(reg + 1, 0)
        self.write8(reg + 2, ticks & 0xFF)
        self.write8(reg + 3, ticks >> 8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", type=int, required=True)
    ap.add_argument("--center", type=int, default=1500)
    ap.add_argument("--delta", type=int, default=90)
    ap.add_argument("--hold", type=float, default=0.55)
    args = ap.parse_args()

    pca = Pca9685()
    sequence = [args.center, args.center + args.delta, args.center - args.delta, args.center]
    for pulse in sequence:
        pca.pulse(args.channel, pulse)
        time.sleep(args.hold)
    print(f"PCA 0x42 CH{args.channel}: {sequence} us")


if __name__ == "__main__":
    main()
