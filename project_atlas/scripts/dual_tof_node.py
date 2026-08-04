import os, sys, time
if 'ROS_DISTRO' not in os.environ:
    os.execvpe('bash', ['bash', '-c', 'source /opt/ros/humble/setup.bash && exec python3 ' + ' '.join(sys.argv)], os.environ)
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32
import board, busio
import Jetson.GPIO as GPIO
import adafruit_vl53l0x

XSHUT_PIN = 25
ADDR_CENTER = 0x29
ADDR_FRONT  = 0x2d

class DualTOFNode(Node):
    def __init__(self):
        super().__init__('dual_tof_node')
        self._pub_center = self.create_publisher(Float32, '/tof/center', 10)
        self._pub_front  = self.create_publisher(Float32, '/tof/front',  10)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(XSHUT_PIN, GPIO.OUT)
        GPIO.output(XSHUT_PIN, GPIO.HIGH)
        time.sleep(0.1)
        i2c = busio.I2C(board.SCL, board.SDA)
        self._s_center = None
        self._s_front  = None
        for addr, name in [(ADDR_CENTER,'center'),(ADDR_FRONT,'front')]:
            for attempt in range(3):
                try:
                    s = adafruit_vl53l0x.VL53L0X(i2c, address=addr, io_timeout=5)
                    if name == 'center': self._s_center = s
                    else:                self._s_front  = s
                    print(f'VL53L0X OK at 0x{addr:02x} ({name})', flush=True)
                    break
                except Exception as e:
                    print(f'attempt {attempt+1} failed at 0x{addr:02x}: {e}', flush=True)
                    time.sleep(0.5)
        self.create_timer(0.1, self._cb)

    def _cb(self):
        for sensor, pub in [(self._s_center, self._pub_center),(self._s_front, self._pub_front)]:
            try:
                val = float(sensor.range) if sensor else -1.0
            except Exception:
                val = -1.0
            pub.publish(Float32(data=val))

def main():
    rclpy.init()
    node = DualTOFNode()
    try: rclpy.spin(node)
    except KeyboardInterrupt: pass
    finally:
        GPIO.cleanup()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()

