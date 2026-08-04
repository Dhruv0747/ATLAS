#!/usr/bin/env python3
"""
ina260_node.py -- ROS2 node for INA260 power monitor (battery %)
IMPORTANT: INA260 default 0x40 conflicts with PCA9685.
  Connect A0 pin to VIN (3.3V) on INA260 board -> address becomes 0x41
  Update INA260_ADDR below to match your wiring.
Topics: /battery/voltage /battery/current /battery/power /battery/percent
Run: nohup python3 /home/jetson/project_atlas/scripts/ina260_node.py > /tmp/ina260.log 2>&1 &
"""
import os, sys
if 'ROS_DISTRO' not in os.environ:
    os.execvpe('bash', ['bash', '-c',
        'source /opt/ros/humble/setup.bash && exec python3 ' + ' '.join(sys.argv)], os.environ)
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32
import board, busio
import adafruit_ina260

INA260_ADDR = 0x41   # CHANGE to 0x41 if A0=VIN, 0x44 if A1=VIN
BATT_FULL   = 12.6   # Volts at 100% (3S LiPo)
BATT_EMPTY  = 10.5   # Volts at 0%

def v_to_pct(v):
    return max(0.0, min(100.0, (v-BATT_EMPTY)/(BATT_FULL-BATT_EMPTY)*100.0))

class INA260Node(Node):
    def __init__(self):
        super().__init__('ina260_node')
        i2c = busio.I2C(board.SCL, board.SDA)
        self._ina = adafruit_ina260.INA260(i2c, address=INA260_ADDR)
        self.get_logger().info(f'INA260 ready at 0x{INA260_ADDR:02X}')
        self._pv  = self.create_publisher(Float32, '/battery/voltage', 10)
        self._pa  = self.create_publisher(Float32, '/battery/current', 10)
        self._pw  = self.create_publisher(Float32, '/battery/power',   10)
        self._pp  = self.create_publisher(Float32, '/battery/percent', 10)
        self.create_timer(1.0, self._cb)

    def _cb(self):
        try:
            v = self._ina.voltage
            a = self._ina.current / 1000.0
            w = self._ina.power / 1000.0
            p = v_to_pct(v)
        except Exception as e:
            self.get_logger().warn(f'INA260 error: {e}')
            return
        self._pv.publish(Float32(data=float(v)))
        self._pa.publish(Float32(data=float(a)))
        self._pw.publish(Float32(data=float(w)))
        self._pp.publish(Float32(data=float(p)))
        self.get_logger().info(f'Battery: {v:.2f}V {a:.2f}A {w:.1f}W {p:.0f}%')

def main():
    rclpy.init(); node = INA260Node()
    try: rclpy.spin(node)
    except KeyboardInterrupt: pass
    finally: node.destroy_node(); rclpy.shutdown()

if __name__ == '__main__': main()
