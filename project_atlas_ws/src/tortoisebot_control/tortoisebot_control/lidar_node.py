#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
import serial
import struct
import math

class LD06Lidar(Node):
    def __init__(self):
        super().__init__('ld06_lidar')
        self.publisher = self.create_publisher(LaserScan, '/scan', 10)
        self.port = '/dev/ttyUSB0'  # change if different
        self.baudrate = 128000
        self.ser = serial.Serial(self.port, self.baudrate, timeout=0.5)
        self.get_logger().info(f'Connected to {self.port}')
        self.timer = self.create_timer(0.05, self.read_scan)  # 20 Hz

    def read_scan(self):
        # Search for packet start (0x54 0x2C)
        while True:
            header = self.ser.read(2)
            if len(header) < 2:
                return
            if header[0] == 0x54 and header[1] == 0x2C:
                break
        # Read remaining packet: 47 bytes (45 after header? actual LD06 packet is 47 bytes total including header? Let's read 47-2=45)
        data = self.ser.read(45)
        if len(data) < 45:
            return
        # Parse packet (simplified for LD06)
        # Byte 0: speed (ignored), byte1: start angle (ignored), then 12 points of 3 bytes each
        # For a full implementation, we'd parse all 12 points. Here's a basic version:
        points = []
        for i in range(12):
            idx = 2 + i*3
            distance = (data[idx] | (data[idx+1] << 8)) / 1000.0  # mm to m
            confidence = data[idx+2]
            if distance > 0.02:  # ignore noise
                points.append(distance)
        if not points:
            return
        # Create LaserScan message
        scan = LaserScan()
        scan.header.frame_id = 'laser_frame'
        scan.header.stamp = self.get_clock().now().to_msg()
        scan.angle_min = -math.pi
        scan.angle_max = math.pi
        scan.angle_increment = (2*math.pi) / len(points) if points else 0.0
        scan.range_min = 0.02
        scan.range_max = 12.0
        scan.ranges = points
        self.publisher.publish(scan)
        self.get_logger().debug(f'Published {len(points)} points')

def main(args=None):
    rclpy.init(args=args)
    node = LD06Lidar()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
