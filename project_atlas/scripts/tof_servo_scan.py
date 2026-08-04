#!/usr/bin/env python3
"""
TOF obstacle avoidance - ROVER 4WDXL60R
Publishes ROS2 /cmd_vel -- rover_driver handles ESP32 serial, no conflict.
ch0=steering servo  ch1=TOF pan servo (sweeps L/C/R)

Run: source ~/tortoisebot_ws/install/setup.bash && python3 /home/jetson/project_atlas/scripts/tof_servo_scan.py
Stop: Ctrl+C
"""
import os
os.environ.setdefault('BLINKA_LGPIO', '1')

import time, board, busio, adafruit_vl53l0x, smbus2
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist

PCA_ADDR = 0x42
STEER_CH = 0
SCAN_CH  = 1

STEER_CENTER = 1500
STEER_LEFT   = 1100
STEER_RIGHT  = 1900

SCAN_LEFT   = 1200
SCAN_CENTER = 1500
SCAN_RIGHT  = 1800

STOP_MM  = 250
CLEAR_MM = 600

SPEED_FWD  = 0.25
SPEED_TURN = 0.15

def pca_init(bus, freq=50):
    bus.write_byte_data(PCA_ADDR, 0x00, 0x10)
    pre = round(25_000_000 / (4096 * freq)) - 1
    bus.write_byte_data(PCA_ADDR, 0xFE, pre)
    bus.write_byte_data(PCA_ADDR, 0x00, 0x80)
    time.sleep(0.005)

def pca_us(bus, ch, us, freq=50):
    off = max(0, min(4095, round(us / (1_000_000 / freq) * 4096)))
    base = 0x06 + ch * 4
    bus.write_i2c_block_data(PCA_ADDR, base, [0, 0, off & 0xFF, (off >> 8) & 0xFF])

def scan(sensor, bus):
    results = {}
    for name, pos_us in [('left', SCAN_LEFT), ('center', SCAN_CENTER), ('right', SCAN_RIGHT)]:
        pca_us(bus, SCAN_CH, pos_us)
        time.sleep(0.15)
        readings = [v for _ in range(3) for v in [sensor.range] if v < 8190]
        time.sleep(0.05)
        results[name] = int(sum(readings) / len(readings)) if readings else 9999
    pca_us(bus, SCAN_CH, SCAN_CENTER)
    return results

def decide(d):
    L, C, R = d['left'], d['center'], d['right']
    if C < STOP_MM and L < STOP_MM and R < STOP_MM:
        return STEER_CENTER, 0.0, 0.0, 'STOP (blocked)'
    if C >= CLEAR_MM:
        return STEER_CENTER, SPEED_FWD, 0.0, 'FORWARD'
    if L > R and L > STOP_MM:
        return STEER_LEFT, SPEED_TURN, 0.5, 'LEFT  (L={}mm)'.format(L)
    if R > L and R > STOP_MM:
        return STEER_RIGHT, SPEED_TURN, -0.5, 'RIGHT (R={}mm)'.format(R)
    if C > STOP_MM:
        return STEER_CENTER, SPEED_TURN * 0.5, 0.0, 'CREEP (C={}mm)'.format(C)
    return STEER_CENTER, 0.0, 0.0, 'STOP (too close)'

def main():
    print("Initialising...")
    i2c    = busio.I2C(board.SCL, board.SDA)
    sensor = adafruit_vl53l0x.VL53L0X(i2c)
    bus    = smbus2.SMBus(1)
    pca_init(bus)
    pca_us(bus, STEER_CH, STEER_CENTER)
    pca_us(bus, SCAN_CH,  SCAN_CENTER)
    time.sleep(0.5)
    print("  VL53L0X + PCA9685 OK")

    rclpy.init()
    node = Node('tof_avoid')
    pub  = node.create_publisher(Twist, '/cmd_vel', 10)
    print("  ROS2 /cmd_vel publisher OK -- no serial conflict")
    print("\nPress Ctrl+C to stop.\n")
    print("{:>8} {:>8} {:>8}   {:<26}  SPEED".format("LEFT","CENTER","RIGHT","ACTION"))
    print("-" * 68)

    try:
        while rclpy.ok():
            result = scan(sensor, bus)
            steer_us, linear, angular, action = decide(result)
            pca_us(bus, STEER_CH, steer_us)
            msg = Twist()
            msg.linear.x  = linear
            msg.angular.z = angular
            pub.publish(msg)
            L, C, R = result['left'], result['center'], result['right']
            print("{:>7}mm {:>7}mm {:>7}mm   {:<26}  {:.2f} m/s".format(L,C,R,action,linear), end='\r')
            time.sleep(0.3)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        stop = Twist()
        pub.publish(stop)
        pca_us(bus, STEER_CH, STEER_CENTER)
        pca_us(bus, SCAN_CH,  SCAN_CENTER)
        bus.close()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
