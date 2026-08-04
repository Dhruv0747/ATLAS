#!/usr/bin/env python3
"""
motor_node.py - TortoiseBot mecanum drive + ST3215 steering servos
2x Waveshare General Driver for Robots (ESP32 UGV01 mode)
  Front board (/dev/esp32_front): FL+FR DC motors + front ST3215 steering servo
  Back  board (/dev/esp32_back):  BL+BR DC motors + rear  ST3215 steering servo
JSON protocol @ 115200 baud:
  {"T":1,"L":<m/s>,"R":<m/s>}             - drive (+-0.5 m/s)

BusServoController: direct FEETECH STS3215 control via Waveshare Bus Servo
  Adapter on /dev/ttyACM0 @ 1,000,000 baud.
  Servo IDs: 1 (front, centre=2261)  4 (rear, centre=1943)
"""
import json, threading, time
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
from geometry_msgs.msg import Twist,Vector3Stamped
from sensor_msgs.msg import JointState, BatteryState
from std_msgs.msg import String
try:
    import serial
    from serial import SerialException
except ImportError:
    raise SystemExit("pip install pyserial --break-system-packages")

MAX_SPEED_MS  = 0.15
MAX_STEER_DEG = 5.0
INIT_DELAY    = 0.10


class WaveshareBoard:
    def __init__(self, port, logger, baud=115200):
        self.port    = port
        self.baud    = baud
        self._log    = logger
        self._serial = None
        self._lock   = threading.Lock()
        self._connect()

    def _open_port(self):
        try:
            self._serial = serial.Serial(self.port, self.baud, timeout=1)
            return True
        except SerialException as e:
            self._log.error(f'[{self.port}] open failed: {e}')
            self._serial = None
            return False

    def _raw_write(self, obj):
        if self._serial and self._serial.is_open:
            self._serial.write((json.dumps(obj) + '\n').encode())

    def _connect(self):
        if not self._open_port():
            return False
        time.sleep(0.05)
        self._raw_write({"T":900})
        time.sleep(INIT_DELAY)
        self._raw_write({"T":136,"cmd":5000})
        time.sleep(INIT_DELAY)
        time.sleep(INIT_DELAY)
        self._log.info(f'[{self.port}] connected and initialised')
        return True

    def _send(self, obj):
        if self._serial is None or not self._serial.is_open:
            if not self._connect():
                return False
        try:
            self._raw_write(obj)
            return True
        except SerialException as e:
            self._log.warning(f'[{self.port}] write error: {e}')
            try: self._serial.close()
            except: pass
            self._serial = None
            return False


    def query_battery(self):
        with self._lock:
            if not self._serial or not self._serial.is_open:
                return None
            try:
                self._serial.reset_input_buffer()
                self._raw_write({"T": 130})
                deadline = time.time() + 0.5
                while time.time() < deadline:
                    line = self._serial.readline()
                    if not line:
                        break
                    try:
                        d = json.loads(line.decode())
                        if d.get("T") == 1001 and "v" in d:
                            self._last_telem=d;return float(d.get("v",0))
                    except Exception:
                        pass
            except Exception:
                pass
        return None

    def set_speeds(self, L, R):
        L = max(-MAX_SPEED_MS, min(MAX_SPEED_MS, L))
        R = max(-MAX_SPEED_MS, min(MAX_SPEED_MS, R))
        with self._lock:
            return self._send({"T": 1, "L": round(L, 4), "R": round(R, 4)})

    def set_steering(self, angle_deg):
        """Positive angle = steer left. Range: +/-45 degrees."""
        angle_deg = max(-MAX_STEER_DEG, min(MAX_STEER_DEG, angle_deg))
        with self._lock:
            pass

    def stop(self):
        self.set_speeds(0.0, 0.0)

    def centre(self):
        self.set_steering(0.0)

    def close(self):
        with self._lock:
            if self._serial and self._serial.is_open:
                try:
                    self._raw_write({"T": 1, "L": 0, "R": 0})
                    time.sleep(0.02)
                    time.sleep(0.05)
                    self._serial.close()
                except: pass


class BusServoController:
    """Direct FEETECH STS3215 control via Waveshare Bus Servo Adapter.

    WritePosEx packet layout (register 0x29, 7 data bytes):
        [0xFF, 0xFF, ID, LEN, CMD=3, 0x29,

    Calibrated servo centres:
        ID 1 (front steering): 2261
        ID 4 (rear  steering): 1943
    """
    CTR = {1: 2253, 4: 1901}
    _HOLD_LIMIT = 5.0
    _BREAK_TIME = 2.0
    _CENTER_EPS = 1.0

    def __init__(self, port='/dev/servo_bus', baud=1000000):
        self._s  = serial.Serial(port, baud, timeout=0.1)
        self._lk = threading.Lock()
        time.sleep(0.2)
        for sid in self.CTR:
            self._wr(sid,0x30,0xE8)
            time.sleep(0.05)
            self._wr(sid,0x31,0x03)
            time.sleep(0.05)
            self._mv(sid,self.CTR[sid],spd=50)
            time.sleep(0.1)
            self._wr(sid,0x28,1)
            time.sleep(1.0)
        for sid in self.CTR:
            self._wr(sid,0x28,0)
        self._tgt = {1: self.CTR[1], 4: self.CTR[4]}
        self._run  = True
        self._th   = threading.Thread(target=self._loop, daemon=True)
        self._th.start()

    def _chk(self, d):
        return (~sum(d)) & 0xFF

    def _wr(self, sid, addr, val):
        """Write a single byte to register addr."""
        d = [sid, 4, 3, addr, val]
        c = self._chk(d)
        with self._lk:
            self._s.write(bytes([0xFF, 0xFF]) + bytes(d) + bytes([c]))
        time.sleep(0.05)

    def _mv(self, sid, pos, spd=300, acc=20):
        """Move servo to pos using Waveshare WritePosEx (start reg 0x29)."""
        pos = max(0, min(4095, int(round(pos))))
        # 7 bytes starting at register 0x29:
        dat = [0x29, acc,
               pos & 0xFF, (pos >> 8) & 0xFF,
               0, 0,
               spd & 0xFF, (spd >> 8) & 0xFF]
        d = [sid, len(dat) + 2, 3] + dat
        c = self._chk(d)
        with self._lk:
            self._s.write(bytes([0xFF, 0xFF]) + bytes(d) + bytes([c]))

    def set_steering(self, fa, ba=None):
        if ba is None:
            ba = 0.0
        scale = 4096/360.0
        fp = max(0, min(4095, int(round(self.CTR[4] - fa * scale))))
        bp = max(0, min(4095, int(round(self.CTR[1] + ba * scale))))
        with self._lk:
            self._tgt[4] = fp
            self._tgt[1] = bp

    def _loop(self):
        hold_since = None
        torque_on  = False
        eps = self._CENTER_EPS * 4096 / 360.0
        while self._run:
            time.sleep(0.1)
            with self._lk:
                t1 = self._tgt[1]
                t4 = self._tgt[4]
            at_ctr = (abs(t1 - self.CTR[1]) < eps and
                      abs(t4 - self.CTR[4]) < eps)
            if at_ctr:
                if torque_on:
                    self._mv(1, self.CTR[1], spd=50)
                    self._mv(4, self.CTR[4], spd=50)
                    time.sleep(0.5)
                    for sid in self.CTR:
                        self._wr(sid, 0x28, 0)
                    torque_on = False
                hold_since = None
            else:
                if not torque_on:
                    for sid in self.CTR:
                        self._wr(sid, 0x28, 1)
                    time.sleep(0.05)
                    self._mv(1, t1, spd=300)
                    self._mv(4, t4, spd=300)
                    torque_on  = True
                    hold_since = time.time()
                elif hold_since and (time.time() - hold_since) > self._HOLD_LIMIT:
                    for sid in self.CTR: self._wr(sid,0x28,0)
                    time.sleep(0.3)
                    for sid in self.CTR: self._wr(sid,0x28,1)
                    time.sleep(0.05)
                    self._mv(1,self.CTR[1],spd=100)
                    self._mv(4,self.CTR[4],spd=100)
                    time.sleep(self._BREAK_TIME)
                    with self._lk:
                        t1 = self._tgt[1]
                        t4 = self._tgt[4]
                    at2 = (abs(t1 - self.CTR[1]) < eps and
                           abs(t4 - self.CTR[4]) < eps)
                    if at2:
                        for sid in self.CTR:
                            self._wr(sid, 0x28, 0)
                        torque_on  = False
                        hold_since = None
                    else:
                        self._mv(1, t1, spd=300)
                        self._mv(4, t4, spd=300)
                        hold_since = time.time()

    def close(self):
        self._run = False
        time.sleep(0.2)
        for sid in self.CTR:
            try: self._wr(sid, 0x28, 0)
            except Exception: pass
        try: self._s.close()
        except Exception: pass

class PCA9685Servo:
    """PWM servo via PCA9685 on TCA9548A mux ch2 (addr 0x40).

    Channel map:
      ch0 = front steering (S8218 40KG, 1500us centre, +-500us at +-45deg)
      ch1 = camera pan
      ch2 = camera tilt
      ch3 = left ultrasonic pan
      ch4 = right ultrasonic pan
    """
    _MODE1     = 0x00
    _PRESCALE  = 0xFE
    _LED0_ON_L = 0x06

    def __init__(self, channel, bus=1, mux_addr=0x70, mux_ch=2,
                 pca_addr=0x40, center_us=1500, range_us=500, max_deg=45):
        import smbus2, time
        self._bus  = smbus2.SMBus(bus)
        self._mux  = mux_addr
        self._msel = 1 << mux_ch
        self._pca  = pca_addr
        self._ch   = channel
        self._cus  = center_us
        self._rus  = range_us
        self._mdeg = max_deg
        # Init PCA9685 with retry (re-select mux before each write to avoid bus contention)
        for _attempt in range(5):
            try:
                self._open_mux()
                self._bus.write_byte_data(self._pca, self._MODE1, 0x00); time.sleep(0.005)
                self._open_mux()
                self._bus.write_byte_data(self._pca, self._MODE1, 0x10)
                self._open_mux()
                self._bus.write_byte_data(self._pca, self._PRESCALE, 121)
                self._open_mux()
                self._bus.write_byte_data(self._pca, self._MODE1, 0x80); time.sleep(0.005)
                break
            except Exception:
                if _attempt == 4: raise
                time.sleep(0.05)

    def _open_mux(self):
        self._bus.write_byte(self._mux, self._msel)

    def _write_pulse(self, us):
        self._open_mux()
        tick = min(4095, int(us * 4096 / 20000))
        reg  = self._LED0_ON_L + 4 * self._ch
        self._bus.write_i2c_block_data(
            self._pca, reg, [0, 0, tick & 0xFF, (tick >> 8) & 0x0F])

    def set_steering(self, angle_deg, ba=None):
        a  = max(-self._mdeg, min(self._mdeg, float(angle_deg)))
        us = self._cus + int(self._rus * a / self._mdeg)
        self._write_pulse(us)

    def set_pulse_us(self, us):
        self._write_pulse(int(us))

    def centre(self):
        self._write_pulse(self._cus)

    def close(self):
        try:
            self.centre()
        except Exception:
            pass


class MotorNode(Node):
    def __init__(self):
        super().__init__('motor_node')
        self.declare_parameter('front_port',       '/dev/esp32_front')
        self.declare_parameter('back_port',        '/dev/esp32_back')
        self.declare_parameter('servo_port', '/dev/servo_bus')
        self.declare_parameter('watchdog_timeout', 1.0)
        # az_scale: angular.z (rad/s) * az_scale = wheel speed delta (m/s)
        self.declare_parameter('az_scale',         0.15)
        # steering_scale: angular.z (rad/s) * steering_scale = servo degrees
        self.declare_parameter('steering_scale', 10.0)
        # back_steer_ratio: rear servo counter-steers by this fraction
        self.declare_parameter('back_steer_ratio', 0.5)

        fp  = self.get_parameter('front_port').value
        bp  = self.get_parameter('back_port').value
        sp  = self.get_parameter('servo_port').value
        self._wdt   = self.get_parameter('watchdog_timeout').value
        self._az    = self.get_parameter('az_scale').value
        self._st_sc = self.get_parameter('steering_scale').value
        self._bk_rt = self.get_parameter('back_steer_ratio').value

        self._front = WaveshareBoard(fp, self.get_logger())
        self._back  = WaveshareBoard(bp, self.get_logger())

        # PWM servo via PCA9685 (TCA9548A mux ch2, ch0 = front steer)
        try:
            self._servo = PCA9685Servo(
                channel=0, center_us=1500, range_us=500, max_deg=45)
            self._servo.centre()
            self.get_logger().info('PCA9685Servo ch0 (front steer) ready')
        except Exception as e:
            self.get_logger().error(f'PCA9685Servo init failed: {e}')
            self._servo = None

        self._js_pub=self.create_publisher(JointState,"joint_states",10)
        self._pub_bat = self.create_publisher(BatteryState, '/battery_state', 10)
        self._pub_ip  = self.create_publisher(String, '/robot_ip', 5)
        self.create_timer(0.1,self._pub_js)
        self._last    = time.time()
        self._stopped = True
        self._imu_baseline=None
        self._tilt_stop=False

        qos = QoSProfile(depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            durability=DurabilityPolicy.VOLATILE)
        self.create_subscription(Twist,'/cmd_vel',self._cb,qos)
        self.create_subscription(Vector3Stamped,'/imu/euler',self._imu_cb,10)
        self.create_timer(0.1, self._watchdog)
        self.create_timer(30.0, self._query_battery)
        self.get_logger().info('motor_node ready - listening on /cmd_vel')

    def _cb(self, msg):
        lx = msg.linear.x
        ly = msg.linear.y
        az = msg.angular.z * self._az  # differential drive turning

        # Mecanum kinematics (m/s) - az=0 means no wheel differential
        fl =  lx - ly - az
        fr =  lx + ly + az
        bl =  lx + ly - az
        br =  lx - ly + az
        s  = max(abs(fl), abs(fr), abs(bl), abs(br), MAX_SPEED_MS) / MAX_SPEED_MS
        fl /= s; fr /= s; bl /= s; br /= s

        self._front.set_speeds(-fl, -fr)
        self._back.set_speeds(br, bl)  # back board L/R channels are physically swapped

        # Steering servo angles from angular.z
        if self._servo is not None:
            fa = msg.angular.z * self._st_sc
            ba = -fa * self._bk_rt
            fa = max(-MAX_STEER_DEG, min(MAX_STEER_DEG, fa))
            ba = max(-MAX_STEER_DEG, min(MAX_STEER_DEG, ba))
            self.get_logger().info(
                f'steer F={fa:.1f} B={ba:.1f} deg')
            self._servo.set_steering(fa)

        self._last    = time.time()
        self._stopped = False
        try:
            import json as _j,os as _o
            _p="/tmp/robot_bat.json"
            _d=_j.load(open(_p)) if _o.path.exists(_p) else {"v":0,"pct":50}
            _d["L"]=round(fl,3);_d["R"]=round(fr,3)
            _j.dump(_d,open(_p,"w"))
        except:pass

    def _pub_js(self):
        try:
            import json as _jj
            _d=_jj.load(open("/tmp/robot_bat.json"))
            js=JointState()
            js.header.stamp=self.get_clock().now().to_msg()
            js.name=["left_wheel","right_wheel"]
            js.velocity=[float(_d.get("L",0)),float(_d.get("R",0))]
            self._js_pub.publish(js)
        except:pass

    def _pub_bat_state(self, voltage, pct):
        """Publish sensor_msgs/BatteryState for Pico 2 LCD and other consumers."""
        msg = BatteryState()
        msg.header.stamp    = self.get_clock().now().to_msg()
        msg.voltage         = float(voltage)
        msg.percentage      = float(pct) / 100.0   # 0.0-1.0
        msg.present         = True
        msg.power_supply_status     = BatteryState.POWER_SUPPLY_STATUS_DISCHARGING
        msg.power_supply_health     = BatteryState.POWER_SUPPLY_HEALTH_GOOD
        msg.power_supply_technology = BatteryState.POWER_SUPPLY_TECHNOLOGY_LIPO
        self._pub_bat.publish(msg)
        ip_msg = String()
        ip_msg.data = f"{voltage:.1f}V {int(pct)}%"
        self._pub_ip.publish(ip_msg)


    def _query_battery(self):
        if not self._stopped:
            return
        v = self._front.query_battery()
        if v is not None:
            pct = max(0, min(100, int((v - 9.0) / (12.6 - 9.0) * 100)))
            try:
                with open("/tmp/robot_bat.json", "w") as f:
                    json.dump({"v":round(v,2),"pct":pct,"L":0.0,"R":0.0,"dt":0.0},f)
            except Exception:
                pass
            self.get_logger().info(f"Battery: {v:.2f}V ({pct}%)")
        self._pub_bat_state(v, pct)

    def _imu_cb(self,msg):
        if self._imu_baseline is None:
            self._imu_baseline=(msg.vector.y,msg.vector.z);return
        by,bz=self._imu_baseline;dy=abs(msg.vector.y-by)
        dz=msg.vector.z-bz
        if dz>180:dz-=360
        elif dz<-180:dz+=360
        if abs(dy)>30 or abs(dz)>30:
            if not self._tilt_stop:
                self.get_logger().warn("TILT STOP dy=%.1f dz=%.1f"%(dy,dz))
                self._front.stop();self._back.stop()
                if self._servo is not None:self._servo.set_steering(0.0)
                self._stopped=True;self._tilt_stop=True
        else:self._tilt_stop=False
    def _watchdog(self):
        if not self._stopped and time.time() - self._last > self._wdt:
            self.get_logger().info('Watchdog: stop + centre steering')
            self._front.stop();  self._back.stop()
            self._front.centre(); self._back.centre()
            if self._servo is not None:
                try:
                    self._servo.set_steering(0.0)
                except Exception:
                    pass
            self._stopped = True

    def destroy_node(self):
        self._front.close(); self._back.close()
        if self._servo is not None:
            try:
                self._servo.set_steering(0.0)
                self._servo.close()
            except Exception:
                pass
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = MotorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
