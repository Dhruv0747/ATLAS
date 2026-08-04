#!/usr/bin/env python3
"""
ultrasonic_node  --  HC-SR04 distance sensors + pan servos

Publishes (10 Hz):
  /ultrasonic/front  sensor_msgs/Range   fixed front sensor
  /ultrasonic/left   sensor_msgs/Range   left  sensor (on pan servo)
  /ultrasonic/right  sensor_msgs/Range   right sensor (on pan servo)

Subscribes:
  /ultrasonic/left_angle   std_msgs/Float32  pan angle deg  (ch3 on PCA9685)
  /ultrasonic/right_angle  std_msgs/Float32  pan angle deg  (ch4 on PCA9685)

GPIO wiring for HC-SR04 (Pi 5 GPIO, BCM numbering):
  Sensor     Trig pin   Echo pin   Notes
  --------   --------   --------   --------------------------------
  front      GPIO 17    GPIO 27    Echo needs 1k/2k voltage divider
  left       GPIO 22    GPIO 23    Echo needs 1k/2k voltage divider
  right      GPIO 24    GPIO 25    Echo needs 1k/2k voltage divider

IMPORTANT: HC-SR04 Echo outputs 5 V.  Pi 5 GPIO max is 3.3 V.
Use a resistor divider: Echo -> 1kOhm -> GPIO_pin -> 2kOhm -> GND
This gives 3.33 V at GPIO which is within spec.

If no GPIO library is available the node runs in STUB mode,
publishing max-range values so the rest of the graph still works.
"""

import math
import time
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Range
from std_msgs.msg import Float32

MAX_RANGE = 4.0
MIN_RANGE = 0.02
FOV_RAD   = math.radians(15)   # HC-SR04 beam angle

SENSORS = {
    'front': {'trig': 17, 'echo': 27},
    'left':  {'trig': 22, 'echo': 23},
    'right': {'trig': 24, 'echo': 25},
}


class PCA9685Ch:
    """Minimal PCA9685 channel driver â€” reuses chip already init'd by motor_node."""
    _LED0 = 0x06
    def __init__(self, ch, bus=1, mux_addr=0x70, mux_ch=2, pca_addr=0x40,
                 center_us=1500, min_us=500, max_us=2500):
        import smbus2
        self._b   = smbus2.SMBus(bus)
        self._ma  = mux_addr; self._mch = 1 << mux_ch
        self._pca = pca_addr; self._ch  = ch
        self._cu  = center_us; self._mn = min_us; self._mx = max_us
    def _mux(self): self._b.write_byte(self._ma, self._mch)
    def set_us(self, us):
        self._mux()
        us   = max(self._mn, min(self._mx, int(us)))
        tick = int(us * 4096 / 20000)
        reg  = self._LED0 + 4 * self._ch
        self._b.write_i2c_block_data(self._pca, reg,
                                     [0, 0, tick & 0xFF, (tick >> 8) & 0x0F])
    def set_deg(self, deg):
        # 90 deg ~ 500 us half-range
        us = self._cu + int(deg * 500.0 / 90.0)
        self.set_us(us)
    def centre(self): self.set_us(self._cu)
    def close(self):
        try: self.centre()
        except Exception: pass


class UltrasonicNode(Node):
    def __init__(self):
        super().__init__('ultrasonic_node')
        self._gpio_ok = False
        self._lines   = {}

        # Publishers
        self._pubs = {
            name: self.create_publisher(Range, f'/ultrasonic/{name}', 10)
            for name in SENSORS
        }

        # Try to open GPIO lines
        try:
            import gpiod
            chip = gpiod.Chip('gpiochip4')   # Pi 5
            for name, cfg in SENSORS.items():
                trig = chip.get_line(cfg['trig'])
                echo = chip.get_line(cfg['echo'])
                trig.request(consumer=f'us_{name}_trig',
                             type=gpiod.LINE_REQ_DIR_OUT, default_vals=[0])
                echo.request(consumer=f'us_{name}_echo',
                             type=gpiod.LINE_REQ_DIR_IN)
                self._lines[name] = (trig, echo)
            self._gpio_ok = True
            self.get_logger().info('Ultrasonic GPIO ready (gpiod)')
        except Exception as e:
            self.get_logger().warn(f'GPIO init failed ({e}) â€” running in STUB mode')

        # Pan servos (ch3=left, ch4=right on PCA9685)
        self._sv_l = None; self._sv_r = None
        try:
            self._sv_l = PCA9685Ch(ch=3, center_us=1500, min_us=600, max_us=2400)
            self._sv_r = PCA9685Ch(ch=4, center_us=1500, min_us=600, max_us=2400)
            self._sv_l.centre(); self._sv_r.centre()
            self.get_logger().info('Ultrasonic pan servos ready: ch3=left, ch4=right')
        except Exception as e:
            self.get_logger().warn(f'Ultrasonic servo init failed: {e}')

        self.create_subscription(Float32, '/ultrasonic/left_angle',
                                 self._cb_sv_l, 10)
        self.create_subscription(Float32, '/ultrasonic/right_angle',
                                 self._cb_sv_r, 10)
        self.create_timer(0.1, self._measure_all)   # 10 Hz
        self.get_logger().info('ultrasonic_node ready')

    # â”€â”€ GPIO measurement â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _ping(self, name):
        """Return distance in metres, or MAX_RANGE on timeout."""
        trig, echo = self._lines[name]
        trig.set_value(1)
        time.sleep(10e-6)
        trig.set_value(0)

        deadline = time.monotonic() + 0.03
        while echo.get_value() == 0:
            if time.monotonic() > deadline:
                return MAX_RANGE

        t0 = time.monotonic()
        deadline2 = t0 + 0.025
        while echo.get_value() == 1:
            if time.monotonic() > deadline2:
                return MAX_RANGE

        return max(MIN_RANGE, min(MAX_RANGE, (time.monotonic() - t0) * 171.5))

    def _measure_all(self):
        now = self.get_clock().now().to_msg()
        for name, pub in self._pubs.items():
            msg = Range()
            msg.header.stamp      = now
            msg.header.frame_id   = f'ultrasonic_{name}_link'
            msg.radiation_type    = Range.ULTRASOUND
            msg.field_of_view     = FOV_RAD
            msg.min_range         = MIN_RANGE
            msg.max_range         = MAX_RANGE
            if self._gpio_ok and name in self._lines:
                try:
                    msg.range = self._ping(name)
                except Exception:
                    msg.range = MAX_RANGE
            else:
                msg.range = MAX_RANGE   # stub
            pub.publish(msg)

    # â”€â”€ Servo callbacks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _cb_sv_l(self, msg):
        if self._sv_l: self._sv_l.set_deg(float(msg.data))

    def _cb_sv_r(self, msg):
        if self._sv_r: self._sv_r.set_deg(float(msg.data))

    def destroy_node(self):
        if self._sv_l: self._sv_l.close()
        if self._sv_r: self._sv_r.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = UltrasonicNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
