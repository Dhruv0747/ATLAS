#!/usr/bin/env python3
"""
camera_servo_node  --  pan/tilt servo control via PCA9685

Topics (subscribe):
  /camera/pan   std_msgs/Float32   angle deg, -90..+90 (+ = right)
  /camera/tilt  std_msgs/Float32   angle deg, -45..+45 (+ = down)

PCA9685 channels (TCA9548A mux ch2, addr 0x40, 50 Hz):
  ch1 = pan  servo  (MG996R or similar, 500-2500 us)
  ch2 = tilt servo  (MG996R or similar, 800-2200 us, 0 deg = level)
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32


class PCA9685Ch:
    """Minimal single-channel PCA9685 driver.  Shares bus/mux with motor_node."""
    _MODE1 = 0x00; _PRESCALE = 0xFE; _LED0 = 0x06
    _initialised = False   # class-level flag: chip already configured by motor_node

    def __init__(self, ch, bus=1, mux_addr=0x70, mux_ch=2, pca_addr=0x40,
                 min_us=500, max_us=2500, center_us=1500):
        import smbus2
        self._b   = smbus2.SMBus(bus)
        self._ma  = mux_addr
        self._mch = 1 << mux_ch
        self._pca = pca_addr
        self._ch  = ch
        self._mn  = min_us; self._mx = max_us; self._cu = center_us
        self._mux()
        if not PCA9685Ch._initialised:
            import time
            self._b.write_byte_data(self._pca, self._MODE1, 0x00); time.sleep(0.005)
            self._b.write_byte_data(self._pca, self._MODE1, 0x10)
            self._b.write_byte_data(self._pca, self._PRESCALE, 121)
            self._b.write_byte_data(self._pca, self._MODE1, 0x80); time.sleep(0.005)
            PCA9685Ch._initialised = True

    def _mux(self):
        self._b.write_byte(self._ma, self._mch)

    def set_us(self, us):
        self._mux()
        us   = max(self._mn, min(self._mx, int(us)))
        tick = int(us * 4096 / 20000)
        reg  = self._LED0 + 4 * self._ch
        self._b.write_i2c_block_data(self._pca, reg,
                                     [0, 0, tick & 0xFF, (tick >> 8) & 0x0F])

    def set_deg(self, deg, center_deg=0.0, deg_per_us=None):
        # Default: 90 deg = 500 us half-range (1 deg ~ 5.56 us)
        if deg_per_us is None:
            half_range_us = (self._mx - self._mn) / 2
            half_range_deg = 90.0
            deg_per_us = half_range_deg / half_range_us
        us = self._cu + (deg - center_deg) / deg_per_us
        self.set_us(us)

    def centre(self): self.set_us(self._cu)

    def close(self):
        try: self.centre()
        except Exception: pass


class CameraServoNode(Node):
    def __init__(self):
        super().__init__('camera_servo_node')
        self._pan = None; self._tilt = None
        try:
            self._pan  = PCA9685Ch(ch=1, min_us=500,  max_us=2500, center_us=1500)
            self._tilt = PCA9685Ch(ch=2, min_us=800,  max_us=2200, center_us=1500)
            self._pan.centre(); self._tilt.centre()
            self.get_logger().info('Camera servos ready: ch1=pan, ch2=tilt')
        except Exception as e:
            self.get_logger().error(f'Camera servo init failed: {e}')

        self.create_subscription(Float32, '/camera/pan',  self._cb_pan,  10)
        self.create_subscription(Float32, '/camera/tilt', self._cb_tilt, 10)
        self.get_logger().info('camera_servo_node ready')

    def _cb_pan(self, msg):
        if self._pan:
            self._pan.set_deg(float(msg.data))

    def _cb_tilt(self, msg):
        if self._tilt:
            self._tilt.set_deg(float(msg.data))

    def destroy_node(self):
        if self._pan:  self._pan.close()
        if self._tilt: self._tilt.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = CameraServoNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
