#!/usr/bin/env python3
"""rover_dashboard.py ??? Professional Rover HMI  (Pi 5 ?? 1024??600)"""
import os, sys, time, math, json, threading, subprocess
# This HMI has no text-entry controls.  Prevent SDL/GNOME from summoning the
# integrated on-screen keyboard when the capacitive touchscreen is used.
os.environ.setdefault('SDL_HINT_ENABLE_SCREEN_KEYBOARD', '0')
os.environ.setdefault('SDL_ENABLE_SCREEN_KEYBOARD', '0')
os.environ.setdefault('SDL_HINT_IME_SHOW_UI', '0')
os.environ.setdefault('GTK_IM_MODULE', 'xim')
import pygame, cv2, numpy as np, psutil

# ?????? ROS 2 ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
import rclpy
from rclpy.node        import Node
from std_msgs.msg      import Bool, Empty, Float32, String, Int32
from sensor_msgs.msg   import LaserScan, Image as RosImage, CompressedImage, NavSatFix, Joy
from nav_msgs.msg      import Odometry
from geometry_msgs.msg import Twist

# ?????? Thread-safe data store with freshness timestamps ??????????????????????????????????????????????????????????????????
class Store:
    def __init__(self): self._d = {}; self._lock = threading.Lock()
    def set(self, **kw):
        t = time.monotonic()
        with self._lock:
            for k, v in kw.items(): self._d[k] = (v, t)
    def get(self, k, default=None):
        with self._lock: r = self._d.get(k); return r[0] if r else default
    def age(self, k):
        with self._lock: r = self._d.get(k); return time.monotonic() - r[1] if r else 999.0

DATA = Store()
THERMAL_HISTORY = []
THERMAL_HISTORY_MAX = 90
AMBIENT_HISTORY = []
AMBIENT_HISTORY_MAX = 180
POWER_IDLE_BASELINE = None
def fresh(k, max_age=2.0): return DATA.age(k) < max_age

def air_quality_label(iaq):
    value = float(iaq)
    if value <= 50: return 'EXCELLENT'
    if value <= 100: return 'GOOD'
    if value <= 150: return 'MODERATE'
    if value <= 200: return 'POOR'
    if value <= 300: return 'UNHEALTHY'
    return 'HAZARDOUS'

# -- Object detection (YOLOv8n background thread) --------------------------
ENABLE_YOLO = True
AI_ACTIVE = True
_detect_model    = None
_detect_results  = []
_detect_result_size = (1, 1)
_detect_lock     = threading.Lock()
_detect_frame    = None
_detect_frame_lk = threading.Lock()

_COCO = ['person','bicycle','car','motorcycle','airplane','bus','train','truck','boat','traffic light','fire hydrant','stop sign','parking meter','bench','bird','cat','dog','horse','sheep','cow','elephant','bear','zebra','giraffe','backpack','umbrella','handbag','tie','suitcase','frisbee','skis','snowboard','sports ball','kite','baseball bat','baseball glove','skateboard','surfboard','tennis racket','bottle','wine glass','cup','fork','knife','spoon','bowl','banana','apple','sandwich','orange','broccoli','carrot','hot dog','pizza','donut','cake','chair','couch','potted plant','bed','dining table','toilet','tv','laptop','mouse','remote','keyboard','cell phone','microwave','oven','toaster','sink','refrigerator','book','clock','vase','scissors','teddy bear','hair drier','toothbrush']
def _load_detector():
    global _detect_model
    try:
        from trt_yolo_detector import TensorRTYOLO
        _detect_model=TensorRTYOLO(
            "/home/jetson/project_atlas/scripts/yolov8n_fp16.engine",
            confidence=0.35
        )
        print("[YOLO] TensorRT FP16 engine loaded OK")
    except Exception as e: print(f"[YOLO] load failed: {e}")

def _detect_loop():
    global _detect_results, _detect_result_size
    while True:
        time.sleep(1.0)
        if not AI_ACTIVE:
            with _detect_lock:
                _detect_results = []
            continue
        if _detect_model is None: continue
        with _detect_frame_lk: f=_detect_frame
        if f is None: continue
        try:
            raw=_detect_model.infer(f)
            # Objects mounted or viewed upside-down are common on a rover.
            # If the normal pass finds nothing, retry at 180 degrees and map
            # the resulting boxes back onto the unchanged camera display.
            if not raw:
                rotated = cv2.rotate(f, cv2.ROTATE_180)
                rotated_raw = _detect_model.infer(rotated)
                fh, fw = f.shape[:2]
                raw = [
                    (fw-x2, fh-y2, fw-x1, fh-y1, ci, cf)
                    for x1, y1, x2, y2, ci, cf in rotated_raw
                ]
            dets=[(x1,y1,x2,y2,_COCO[ci] if ci<len(_COCO) else str(ci),cf)
                  for x1,y1,x2,y2,ci,cf in raw]
            with _detect_lock:
                _detect_results=dets
                _detect_result_size=(f.shape[1], f.shape[0])
        except Exception: pass
if ENABLE_YOLO:
    threading.Thread(target=_load_detector,daemon=True).start()
    threading.Thread(target=_detect_loop,daemon=True).start()

# ?????? ROS node ?????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
class DashNode(Node):
    def __init__(self):
        super().__init__('rover_dashboard')
        S = self.create_subscription
        # Motors
        S(Float32, '/motors/left',       lambda m: DATA.set(motor_left=m.data,  fl=m.data, rl=m.data), 10)
        S(Float32, '/motors/right',      lambda m: DATA.set(motor_right=m.data, fr=m.data, rr=m.data), 10)
        S(Float32, '/motor/front_left',  lambda m: DATA.set(fl=m.data),  10)
        S(Float32, '/motor/front_right', lambda m: DATA.set(fr=m.data),  10)
        S(Float32, '/motor/rear_left',   lambda m: DATA.set(rl=m.data),  10)
        S(Float32, '/motor/rear_right',  lambda m: DATA.set(rr=m.data),  10)
        S(Float32, '/motor_speed',       lambda m: DATA.set(enc_speed=m.data), 10)
        S(Int32, '/yahboom/encoder/m1', lambda m: DATA.set(enc_m1=m.data), 10)
        S(Int32, '/yahboom/encoder/m2', lambda m: DATA.set(enc_m2=m.data), 10)
        S(Int32, '/yahboom/encoder/m3', lambda m: DATA.set(enc_m3=m.data), 10)
        S(Int32, '/yahboom/encoder/m4', lambda m: DATA.set(enc_m4=m.data), 10)
        wheel_keys = ('fr', 'fl', 'br', 'bl')
        wheel_names = ('front_right', 'front_left', 'back_right', 'back_left')
        for key, name in zip(wheel_keys, wheel_names):
            S(Float32, f'/yahboom/wheel/{name}/rpm', lambda m, k=key: DATA.set(**{f'{k}_rpm':m.data}), 10)
            S(Float32, f'/yahboom/wheel/{name}/speed_mps', lambda m, k=key: DATA.set(**{f'{k}_mps':m.data}), 10)
            S(Float32, f'/yahboom/wheel/{name}/distance_m', lambda m, k=key: DATA.set(**{f'{k}_distance':m.data}), 10)
        # Steering
        S(Float32, '/steering/angle',    lambda m: DATA.set(steering=m.data), 10)
        S(Float32, '/servo/angle',       lambda m: DATA.set(steering=m.data), 10)
        S(Float32, '/steering/front_angle_deg', lambda m: DATA.set(front_steer=m.data, steering=m.data), 10)
        S(Float32, '/steering/rear_angle_deg',  lambda m: DATA.set(rear_steer=m.data), 10)
        S(String,  '/steering/mode',            lambda m: DATA.set(steer_mode=m.data), 10)
        # IMU
        S(Float32, '/imu/heading', lambda m: DATA.set(heading=m.data), 10)
        S(Float32, '/imu/roll',    lambda m: DATA.set(roll=m.data),    10)
        S(Float32, '/imu/pitch',   lambda m: DATA.set(pitch=m.data),   10)
        S(Float32, '/imu/yaw',     lambda m: DATA.set(yaw=m.data),     10)
        S(Float32, '/yahboom/imu/heading', lambda m: DATA.set(yb_heading=m.data), 10)
        S(Float32, '/yahboom/imu/roll',    lambda m: DATA.set(yb_roll=m.data),    10)
        S(Float32, '/yahboom/imu/pitch',   lambda m: DATA.set(yb_pitch=m.data),   10)
        S(String,  '/imu/dashboard_json',  self._imu_dashboard, 10)
        # Power ??? tolerate up to 10s between publishes
        S(Float32, '/battery/voltage', lambda m: DATA.set(voltage=m.data),  10)
        S(Float32, '/battery/current', lambda m: DATA.set(current=m.data),  10)
        S(Float32, '/battery/percent', lambda m: DATA.set(bat_pct=m.data),  10)
        S(String,  '/bms/status',      lambda m: DATA.set(bms_status=m.data), 10)
        S(Float32, '/bms/voltage',     lambda m: DATA.set(bms_voltage=m.data), 10)
        S(Float32, '/bms/current',     lambda m: DATA.set(bms_current=m.data), 10)
        S(Float32, '/bms/percent',     lambda m: DATA.set(bms_pct=m.data), 10)
        S(Float32, '/bms/power',       lambda m: DATA.set(bms_power=m.data), 10)
        S(Float32, '/bms/cell1_voltage', lambda m: DATA.set(bms_cell1=m.data), 10)
        S(Float32, '/bms/cell2_voltage', lambda m: DATA.set(bms_cell2=m.data), 10)
        S(Float32, '/bms/cell3_voltage', lambda m: DATA.set(bms_cell3=m.data), 10)
        S(Float32, '/bms/cell4_voltage', lambda m: DATA.set(bms_cell4=m.data), 10)
        # Range
        S(Float32, '/tof/center',   lambda m: DATA.set(tof=m.data), 10)
        S(Float32, '/tof/distance', lambda m: DATA.set(tof=m.data), 10)
        S(String, '/radar/targets', lambda m: DATA.set(radar=m.data), 10)
        S(String, '/thermal/amg8833/status', lambda m: DATA.set(thermal_status=m.data), 10)
        S(String, '/thermal/amg8833/json', self._thermal, 10)
        S(Float32, '/environment/outside_temperature_c', self._ambient_temperature, 10)
        S(Float32, '/environment/outside_humidity_pct', lambda m: DATA.set(outside_humidity=m.data), 10)
        S(Float32, '/environment/pressure_hpa', lambda m: DATA.set(outside_pressure=m.data), 10)
        S(Float32, '/environment/gas_resistance_ohm', lambda m: DATA.set(outside_gas=m.data), 10)
        S(Float32, '/environment/iaq', lambda m: DATA.set(outside_iaq=m.data, outside_air_quality=air_quality_label(m.data)), 10)
        S(Float32, '/environment/eco2_ppm', lambda m: DATA.set(outside_eco2=m.data), 10)
        S(String, '/environment/bme680/json', lambda m: DATA.set(bme680_json=m.data), 10)
        S(String, '/environment/outside_status', lambda m: DATA.set(outside_status=m.data), 10)
        S(Float32, '/ultrasonic/front_mm', lambda m: DATA.set(us_front=m.data), 10)
        S(Float32, '/ultrasonic/left_mm',  lambda m: DATA.set(us_left=m.data), 10)
        S(Float32, '/ultrasonic/right_mm', lambda m: DATA.set(us_right=m.data), 10)
        S(String,  '/ultrasonic/status',   lambda m: DATA.set(us_status=m.data), 10)
        S(String,  '/atlas/recovery_status', lambda m: DATA.set(recovery_status=m.data), 10)
        S(String,  '/atlas/recovery_state',  self._recovery_state, 10)
        S(String,  '/atlas/safety_status',   lambda m: DATA.set(safety_status=m.data), 10)
        S(String,  '/atlas/mission_status',  lambda m: DATA.set(mission_status=m.data), 10)
        S(String,  '/atlas/voice/state',     lambda m: DATA.set(agent_state=m.data), 10)
        S(String,  '/atlas/voice/action',    lambda m: DATA.set(agent_action=m.data), 10)
        S(String,  '/atlas/voice/transcript',lambda m: DATA.set(voice_transcript=m.data), 10)
        S(String,  '/atlas/voice/response',  lambda m: DATA.set(voice_response=m.data), 10)
        S(String,  '/atlas/voice/confirmation',lambda m: DATA.set(voice_confirmation=m.data), 10)
        S(String,  '/atlas/voice/mode',      lambda m: DATA.set(voice_mode=m.data), 10)
        S(String,  '/atlas/voice/cloud',     lambda m: DATA.set(voice_cloud=m.data), 10)
        S(String,  '/voice/vc02/status',   lambda m: DATA.set(voice_status=m.data), 10)
        S(String,  '/voice/vc02/raw',      lambda m: DATA.set(voice_raw=m.data), 10)
        S(Bool,    '/atlas/ai_enabled',     self._ai_enabled, 10)
        S(String,  '/atlas/camera_tracking/status', self._tracking_status, 10)
        S(Int32,   '/camera/bottom_servo_us', lambda m: DATA.set(camera_pan_us=m.data), 10)
        S(Int32,   '/camera/second_servo_us', lambda m: DATA.set(camera_tilt_us=m.data), 10)
        S(Joy,     '/joy', lambda m: DATA.set(joy=(len(m.axes), len(m.buttons))), 10)
        # 5G HAT / GNSS
        S(Bool,    '/cellular/connected',      lambda m: DATA.set(cell_connected=m.data), 10)
        S(Float32, '/cellular/signal_percent', lambda m: DATA.set(cell_signal=m.data), 10)
        S(String,  '/cellular/access_tech',    lambda m: DATA.set(cell_tech=m.data), 10)
        S(String,  '/cellular/operator',       lambda m: DATA.set(cell_operator=m.data), 10)
        S(String,  '/cellular/registration',   lambda m: DATA.set(cell_reg=m.data), 10)
        S(Float32, '/cellular/hat_voltage',    lambda m: DATA.set(hat_voltage=m.data), 10)
        S(Float32, '/cellular/hat_current',    lambda m: DATA.set(hat_current=m.data), 10)
        S(Float32, '/cellular/hat_power',      lambda m: DATA.set(hat_power=m.data), 10)
        S(String,  '/cellular/hat_status',     lambda m: DATA.set(hat_status=m.data), 10)
        S(String,  '/ups/status',              lambda m: DATA.set(ups_status=m.data), 10)
        S(Float32, '/ups/battery_voltage',     lambda m: DATA.set(ups_bat_voltage=m.data), 10)
        S(Float32, '/ups/battery_current',     lambda m: DATA.set(ups_bat_current=m.data), 10)
        S(Float32, '/ups/battery_power',       lambda m: DATA.set(ups_bat_power=m.data), 10)
        S(Float32, '/ups/battery_percent',     lambda m: DATA.set(ups_bat_percent=m.data), 10)
        S(Float32, '/ups/vbus_voltage',        lambda m: DATA.set(ups_vbus_voltage=m.data), 10)
        S(Float32, '/ups/vbus_current',        lambda m: DATA.set(ups_vbus_current=m.data), 10)
        S(Float32, '/ups/vbus_power',          lambda m: DATA.set(ups_vbus_power=m.data), 10)
        S(Float32, '/ups/battery_remaining_mah', lambda m: DATA.set(ups_remaining_mah=m.data), 10)
        S(Float32, '/ups/cell1_voltage',       lambda m: DATA.set(ups_cell1=m.data), 10)
        S(Float32, '/ups/cell2_voltage',       lambda m: DATA.set(ups_cell2=m.data), 10)
        S(Float32, '/ups/cell3_voltage',       lambda m: DATA.set(ups_cell3=m.data), 10)
        S(Float32, '/ups/cell4_voltage',       lambda m: DATA.set(ups_cell4=m.data), 10)
        S(Bool,    '/ups/charging',            lambda m: DATA.set(ups_charging=m.data), 10)
        S(String,  '/ups/charge_state',        lambda m: DATA.set(ups_charge_state=m.data), 10)
        S(Float32, '/gps/satellites',          lambda m: DATA.set(gps_sats=m.data), 10)
        S(Float32, '/gps/hdop',                lambda m: DATA.set(gps_hdop=m.data), 10)
        S(String,  '/gps/constellations',      lambda m: DATA.set(gps_const=m.data), 10)
        S(NavSatFix, '/gps/fix',               self._gps_fix, 10)
        # Navigation
        S(LaserScan, '/scan',    self._scan, 10)
        S(Odometry,  '/odom',    self._odom, 10)
        S(Twist,     '/cmd_vel', self._cmd,  10)
        # Camera via ROS topic (avoids /dev/video0 conflict with explore node)
        self._cam_frame = None
        self._last_cam_store = 0.0
        self._last_compressed_camera = 0.0
        self._last_scan_store = 0.0
        self._cam_lock  = threading.Lock()
        S(CompressedImage, '/camera/image_raw/compressed', self._cam_jpeg_cb, 1)
        S(RosImage, '/camera/image_raw', self._cam_cb, 1)
        # Heartbeat timer instead of broken /rosout String subscription
        self.create_timer(1.0, lambda: DATA.set(ros_hb=int(rclpy.ok())))
        # Touch HMI outputs. Autonomous movement is protected by a long press;
        # raw touch driving is intentionally not latched.
        self.touch_stop_pub = self.create_publisher(Twist, '/cmd_vel_web', 10)
        self.touch_preempt_pub = self.create_publisher(Empty, '/preempt_teleop', 10)
        self.touch_ai_pub = self.create_publisher(Bool, '/atlas/ai_enabled', 10)
        self.touch_face_pub = self.create_publisher(Bool, '/atlas/camera_tracking/enabled', 10)
        self.touch_pan_pub = self.create_publisher(Int32, '/camera/bottom_servo_cmd_us', 10)
        self.touch_tilt_pub = self.create_publisher(Int32, '/camera/second_servo_cmd_us', 10)
        self.touch_start_pub = self.create_publisher(Empty, '/atlas/start_exploration', 10)
        self.touch_stop_mission_pub = self.create_publisher(Empty, '/atlas/stop_exploration', 10)
        self.touch_home_pub = self.create_publisher(Empty, '/atlas/set_home', 10)
        self.touch_return_pub = self.create_publisher(Empty, '/atlas/return_home', 10)

    def _ai_enabled(self, message):
        global AI_ACTIVE, _detect_results
        AI_ACTIVE = bool(message.data)
        if not AI_ACTIVE:
            with _detect_lock:
                _detect_results = []
        DATA.set(ai_enabled=AI_ACTIVE)

    def _tracking_status(self, message):
        text = message.data or ''
        DATA.set(face_tracking_status=text,
                 face_tracking_enabled=not text.startswith('OFF:'))

    def _recovery_state(self, message):
        try:
            DATA.set(recovery_state=json.loads(message.data or '{}'))
        except Exception:
            DATA.set(recovery_state={})

    def _imu_dashboard(self, message):
        try:
            DATA.set(imu_full=json.loads(message.data or '{}'))
        except Exception:
            DATA.set(imu_full={})

    def _thermal(self, m):
        try:
            d = json.loads(m.data or '{}')
            mn = float(d.get('min_c', 0.0) or 0.0)
            mx = float(d.get('max_c', 0.0) or 0.0)
            avg = float(d.get('avg_c', 0.0) or 0.0)
            if d.get('ok'):
                THERMAL_HISTORY.append((time.monotonic(), mn, mx, avg))
                del THERMAL_HISTORY[:-THERMAL_HISTORY_MAX]
            DATA.set(thermal_json=d,
                     thermal_ok=1 if d.get('ok') else 0,
                     thermal_min=mn,
                     thermal_max=mx,
                     thermal_avg=avg,
                     thermal_center=d.get('center_c', 0.0),
                     thermal_addr=d.get('addr', '--'))
        except Exception:
            DATA.set(thermal_ok=0)
    def _ambient_temperature(self, m):
        value = float(m.data)
        AMBIENT_HISTORY.append((time.monotonic(), value))
        del AMBIENT_HISTORY[:-AMBIENT_HISTORY_MAX]
        DATA.set(outside_temperature=value)
    def _scan(self, m):
        now = time.monotonic()
        if now - self._last_scan_store < 0.50:
            return
        self._last_scan_store = now
        ranges = []
        front = []
        left = []
        right = []
        for i, r in enumerate(m.ranges):
            if not (0.01 < r < 10.0):
                continue
            ranges.append(r)
            deg = math.degrees(m.angle_min + i * m.angle_increment)
            if -25 <= deg <= 25:
                front.append(r)
            elif 35 <= deg <= 115:
                left.append(r)
            elif -115 <= deg <= -35:
                right.append(r)
        DATA.set(scan_ok=1, scan_pts=len(ranges),
                 lidar_min=min(ranges) * 1000 if ranges else -1.0,
                 lidar_front=min(front) * 1000 if front else -1.0,
                 lidar_left=min(left) * 1000 if left else -1.0,
                 lidar_right=min(right) * 1000 if right else -1.0)
    def _odom(self, m):
        DATA.set(odom_ok=1,
                 pos_x=m.pose.pose.position.x,
                 pos_y=m.pose.pose.position.y)

    def _cmd(self, m):
        DATA.set(cmd_lin=m.linear.x, cmd_ang=m.angular.z)

    def _gps_fix(self, m):
        DATA.set(gps_status=m.status.status,
                 gps_lat=m.latitude,
                 gps_lon=m.longitude)

    def _cam_jpeg_cb(self, msg):
        now = time.monotonic()
        if now - self._last_cam_store < 0.50:
            return
        try:
            jpg = np.frombuffer(msg.data, dtype=np.uint8)
            bgr = cv2.imdecode(jpg, cv2.IMREAD_COLOR)
            if bgr is None:
                return
            arr = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            self._last_cam_store = now
            self._last_compressed_camera = now
            with self._cam_lock:
                self._cam_frame = arr
            DATA.set(camera_frame_ok=1)
        except Exception:
            pass
    def _cam_cb(self, msg):
        now = time.monotonic()
        if now - self._last_compressed_camera < 2.0:
            return
        if now - self._last_cam_store < 0.50:
            return
        self._last_cam_store = now
        try:
            n_ch = 4 if msg.encoding in ('bgra8','rgba8') else 3
            arr = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.width, n_ch)
            if msg.encoding == 'bgra8':
                arr = arr[:, :, [2, 1, 0]]  # BGRA -> RGB
            elif msg.encoding == 'rgba8':
                arr = arr[:, :, :3]         # RGBA -> RGB
            elif msg.encoding == 'bgr8':
                arr = arr[:, :, ::-1]       # BGR  -> RGB
            with self._cam_lock:
                self._cam_frame = arr.copy()
            DATA.set(camera_frame_ok=1)
        except Exception:
            pass


# ?????? Init ROS in main thread (must NOT be inside a thread lambda) ??????????????????????????????
rclpy.init()
_dash_node = DashNode()
threading.Thread(target=lambda: rclpy.spin(_dash_node), daemon=True).start()

# ?????? System helpers ???????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
def cpu_temp():
    try:
        return f'{float(open("/sys/class/thermal/thermal_zone0/temp").read())/1000:.0f}C'
    except:
        try:
            out = subprocess.check_output(['vcgencmd','measure_temp'],text=True)
            return out.replace('temp=','').replace("'C",'').strip()+'C'
        except: return '--'

def gpu_load_percent():
    """Read Jetson GPU utilisation (kernel reports 0..1000)."""
    for path in (
        '/sys/devices/platform/17000000.gpu/load',
        '/sys/devices/gpu.0/load',
        '/sys/class/devfreq/17000000.gpu/load',
    ):
        try:
            with open(path, 'r', encoding='ascii') as handle:
                return max(0.0, min(100.0, float(handle.read().strip()) / 10.0))
        except (OSError, ValueError):
            continue
    return None

def ip_addr():
    try:
        out = subprocess.check_output(['hostname','-I'],text=True).split()
        return out[0] if out else '?.?.?.?'
    except: return '?.?.?.?'

def net_status():
    info = {
        'wifi_ip': '--', 'wifi_ssid': '--', 'cell_ip': '--',
        'ts_ip': '--', 'route': '--', 'ssh': '--',
        'cell_signal': 0.0, 'cell_tech': '--', 'cell_operator': '--'
    }
    try:
        out = subprocess.check_output(['ip', '-4', '-br', 'addr'], text=True, timeout=1.5)
        for line in out.splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            iface, state, ip = parts[0], parts[1], parts[2].split('/')[0]
            if iface.startswith('wl') and state == 'UP':
                info['wifi_ip'] = ip
            elif iface.startswith(('wwan', 'enx', 'usb')) and state in ('UP', 'UNKNOWN'):
                info['cell_ip'] = ip
            elif iface == 'tailscale0':
                info['ts_ip'] = ip
    except Exception:
        pass
    try:
        route = subprocess.check_output(['ip', '-4', 'route', 'show', 'default'], text=True, timeout=1.5)
        routes = []
        for line in route.splitlines():
            fields = line.split()
            if 'dev' not in fields:
                continue
            iface = fields[fields.index('dev') + 1]
            metric = int(fields[fields.index('metric') + 1]) if 'metric' in fields else 0
            routes.append((metric, iface))
        if routes:
            metric, iface = min(routes)
            if iface.startswith('wl'):
                info['route'] = f'WIFI m{metric}'
            elif iface.startswith(('wwan', 'enx', 'usb')):
                info['route'] = f'5G m{metric}'
            else:
                info['route'] = f'{iface} m{metric}'
    except Exception:
        pass
    try:
        active = subprocess.check_output(
            ['nmcli', '-t', '-f', 'TYPE,DEVICE,NAME', 'connection', 'show', '--active'],
            text=True, timeout=2.0
        )
        for line in active.splitlines():
            fields = line.split(':', 2)
            if len(fields) == 3 and fields[0] == '802-11-wireless':
                info['wifi_ssid'] = fields[2]
    except Exception:
        pass
    try:
        modem = subprocess.check_output(['mmcli', '-m', '0', '-K'], text=True, timeout=3.0)
        for line in modem.splitlines():
            if ':' not in line:
                continue
            key, value = [part.strip() for part in line.split(':', 1)]
            if key == 'modem.generic.signal-quality.value':
                info['cell_signal'] = float(value)
            elif key == 'modem.generic.access-technologies.value[1]':
                info['cell_tech'] = value
            elif key == 'modem.3gpp.operator-name':
                info['cell_operator'] = value
    except Exception:
        pass
    try:
        ss = subprocess.check_output(['ss', '-tn', 'state', 'established'], text=True, timeout=1.5)
        peers = []
        for line in ss.splitlines():
            if ':22 ' not in line:
                continue
            parts = line.split()
            if len(parts) >= 4:
                peer = parts[-1].rsplit(':', 1)[0].strip('[]')
                if peer and peer not in peers:
                    peers.append(peer)
        if peers:
            peer = peers[-1]
            if peer.startswith('192.168.1.'):
                info['ssh'] = 'WIFI ' + peer
            elif peer.startswith('100.'):
                info['ssh'] = 'TS/5G ' + peer
            else:
                info['ssh'] = peer[:16]
    except Exception:
        pass
    return info

# ?????? Colour palette ???????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
BG     = (  4,   8,  16)
PANEL  = (  9,  18,  31)
BORDER = ( 72, 120, 165)
HDR    = (  8,  36,  64)
ACCENT = (  0, 210, 255)
WHITE  = (245, 250, 255)
DIM    = (190, 218, 238)
GREEN  = ( 35, 235, 120)
YELLOW = (255, 210,  40)
RED    = (255,  70,  70)
ORANGE = (255, 145,  35)

# ?????? Pygame bootstrap ????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
os.environ.setdefault('DISPLAY', ':0')
os.environ.setdefault('SDL_IME_SHOW_UI', '0')
pygame.init()
pygame.key.stop_text_input()
pygame.mouse.set_visible(False)
# FULLSCREEN covers GNOME panels/dock completely. Use the real HDMI size for 10 inch screens.
try:
    _info = pygame.display.Info()
    W, H = max(1024, int(_info.current_w or 1024)), max(600, int(_info.current_h or 600))
except Exception:
    W, H = 1024, 600
screen = pygame.display.set_mode((W, H), pygame.FULLSCREEN)
pygame.display.set_caption('Rover HMI')
clock  = pygame.time.Clock()

_font_scale = 1.0 if W < 1200 else min(1.25, W / 1024.0)
F10 = pygame.font.SysFont('monospace', int(10 * _font_scale))
F13 = pygame.font.SysFont('monospace', int(13 * _font_scale))
F15 = pygame.font.SysFont('monospace', int(15 * _font_scale), bold=True)
F18 = pygame.font.SysFont('monospace', int(18 * _font_scale), bold=True)
F22 = pygame.font.SysFont('monospace', int(22 * _font_scale), bold=True)

ATLAS_LOGO_PATHS = [
    '/home/jetson/project_atlas/scripts/atlas_rover_logo_preferred.png',
    '/home/jetson/project_atlas/scripts/atlas_boot_logo.png',
    '/home/jetson/project_atlas/scripts/atlas_rover_logo_preferred.png',
]
ATLAS_LOGO = None
for _logo_path in ATLAS_LOGO_PATHS:
    if os.path.exists(_logo_path):
        try:
            ATLAS_LOGO = pygame.image.load(_logo_path).convert_alpha()
            break
        except Exception:
            ATLAS_LOGO = None

# Camera uses ROS /camera/image_raw only. Do not open /dev/video0 here; camera_ros owns it.
CAM_W, CAM_H = 640, 360
_cam_ok = False

# ?????? Layout ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
SEP_Y  = 360
INFO_X = CAM_W
INFO_W = W - INFO_X
PWR_H  = 148
TITLE_H = 34
HDG_H  = SEP_Y - PWR_H

BC = [0, 200, 470, 720, W]

# ?????? Drawing helpers ???????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

def parse_radar_targets(raw):
    out = []
    if not raw:
        return out
    for part in [p.strip() for p in raw.split('|') if p.strip()]:
        try:
            label = part.split(':', 1)[0] if ':' in part else f'T{len(out)+1}'
            xm = int(part.split('x=')[1].split('mm')[0])
            ym = int(part.split('y=')[1].split('mm')[0])
            spd = 0
            if 'spd=' in part:
                spd = int(part.split('spd=')[1].split('cm/s')[0])
            dist = math.hypot(xm, ym)
            out.append({'label': label, 'x': xm, 'y': ym, 'speed': spd, 'dist': dist})
        except Exception:
            pass
    return out

def draw_radar_ppi(cx, cy, r, targets, t):
    bg = (0, 20, 14)
    ring = (0, 95, 62)
    line = (0, 150, 95)
    sweep = (0, 255, 120)
    max_range = 3000.0
    pygame.draw.circle(screen, bg, (cx, cy), r)
    pygame.draw.circle(screen, (0, 230, 140), (cx, cy), r, 2)
    for d in [500, 1000, 2000, 3000]:
        rr = int(r * d / max_range)
        pygame.draw.circle(screen, ring, (cx, cy), rr, 1)
        if d in (1000, 2000, 3000):
            screen.blit(F10.render(f'{d//1000}m', True, DIM), (cx + rr - 8, cy + 2))
    pygame.draw.line(screen, line, (cx - r, cy), (cx + r, cy), 1)
    pygame.draw.line(screen, line, (cx, cy - r), (cx, cy + r), 1)
    pygame.draw.arc(screen, line, (cx-r, cy-r, r*2, r*2), math.radians(205), math.radians(335), 1)

    ang = (t * 80) % 360
    rad = math.radians(ang - 90)
    ex = cx + int(r * math.cos(rad))
    ey = cy + int(r * math.sin(rad))
    pygame.draw.line(screen, sweep, (cx, cy), (ex, ey), 2)

    for tgt in targets[:3]:
        xm, ym, spd = tgt['x'], tgt['y'], tgt['speed']
        if ym <= 0:
            continue
        bx = cx + int(xm * r / max_range)
        by = cy - int(ym * r / max_range)
        if (bx - cx) ** 2 + (by - cy) ** 2 <= r * r:
            col = RED if tgt['dist'] < 500 else (YELLOW if tgt['dist'] < 1000 else GREEN)
            pygame.draw.circle(screen, col, (bx, by), 6)
            pygame.draw.circle(screen, WHITE, (bx, by), 2)
            if spd:
                pygame.draw.line(screen, col, (bx, by), (bx, by - max(-18, min(18, spd // 2))), 2)
            screen.blit(F10.render(tgt['label'], True, col), (bx + 7, by - 8))

def draw_panel(x, y, w, h, title=None, tcol=ACCENT):
    pygame.draw.rect(screen, PANEL,  (x, y, w, h))
    pygame.draw.rect(screen, BORDER, (x, y, w, h), 1)
    if title:
        pygame.draw.rect(screen, HDR, (x+1, y+1, w-2, 22))
        screen.blit(F15.render(title, True, tcol), (x+8, y+3))
        return y + 28
    return y + 4

def draw_bar(x, y, w, h, pct, color=GREEN):
    pygame.draw.rect(screen, (28,36,56), (x, y, w, h))
    pygame.draw.rect(screen, BORDER,     (x, y, w, h), 1)
    fill = max(0, min(int(abs(pct)/100*(w-2)), w-2))
    if fill: pygame.draw.rect(screen, color, (x+1, y+1, fill, h-2))

def draw_signal_bars(x, y, pct, live=True):
    pct = max(0, min(100, int(pct or 0)))
    active = 0 if not live else max(1 if pct > 0 else 0, min(5, int(math.ceil(pct / 20.0))))
    col = GREEN if pct >= 60 else (YELLOW if pct >= 30 else RED)
    for i in range(5):
        h = 5 + i * 4
        bx = x + i * 9
        by = y + 22 - h
        c = col if i < active else (35, 45, 65)
        pygame.draw.rect(screen, c, (bx, by, 6, h))
        pygame.draw.rect(screen, BORDER, (bx, by, 6, h), 1)

def parse_constellations(raw):
    out = {'GPS': 0, 'GLONASS': 0, 'GALILEO': 0, 'BEIDOU': 0, 'QZSS': 0, 'NAVIC': 0}
    if not raw:
        return out
    for part in str(raw).split('|'):
        if ':' not in part:
            continue
        k, v = part.split(':', 1)
        k = k.strip().upper()
        if k in out:
            try:
                out[k] = max(0, int(float(v)))
            except Exception:
                pass
    return out

def draw_constellation_bars(x, y, counts, live=True):
    labels = [
        ('GPS US', 'GPS', GREEN),
        ('GLO RU', 'GLONASS', (70, 180, 255)),
        ('BDS CN', 'BEIDOU', ORANGE),
        ('GAL EU', 'GALILEO', (170, 120, 255)),
        ('QZSS JP', 'QZSS', (255, 205, 70)),
        ('NAV IN', 'NAVIC', (255, 80, 120)),
    ]
    max_sat = 12.0
    for i, (label, key, col) in enumerate(labels):
        column = i % 2
        row = i // 2
        xx = x + column * 122
        yy = y + row * 17
        val = counts.get(key, 0) if live else 0
        fill = int(min(val, max_sat) / max_sat * 48)
        c = col if val > 0 and live else (45, 55, 72)
        screen.blit(F10.render(label, True, c), (xx, yy))
        pygame.draw.rect(screen, (26, 34, 50), (xx + 43, yy + 2, 50, 8))
        if fill:
            pygame.draw.rect(screen, c, (xx + 44, yy + 3, fill, 6))
        pygame.draw.rect(screen, BORDER, (xx + 43, yy + 2, 50, 8), 1)
        screen.blit(F10.render(f'{val:2d}', True, c), (xx + 98, yy))

def draw_status(x, y, label, ok, note=''):
    c = GREEN if ok else RED
    pygame.draw.circle(screen, c,      (x+8, y+9), 6)
    pygame.draw.circle(screen, BORDER, (x+8, y+9), 6, 1)
    screen.blit(F15.render(f'{label:<6}', True, WHITE), (x+20, y+1))
    screen.blit(F15.render('OK' if ok else '--', True, c), (x+110, y+1))
    if note: screen.blit(F10.render(note, True, DIM), (x+20, y+18))
    return y + (30 if note else 22)


def range_color(mm, live=True):
    if not live or mm is None or mm < 0:
        return RED
    if mm < 450:
        return RED
    if mm < 900:
        return YELLOW
    return GREEN

def scaled_logo(max_w, max_h):
    if ATLAS_LOGO is None:
        return None
    src_w, src_h = ATLAS_LOGO.get_size()
    scale = min(max_w / max(src_w, 1), max_h / max(src_h, 1))
    return pygame.transform.smoothscale(ATLAS_LOGO, (int(src_w * scale), int(src_h * scale)))

def sensor_word(mm, live=True):
    if not live or mm is None or mm < 0:
        return 'NO DATA', RED
    if mm < 450:
        return 'STOP', RED
    if mm < 900:
        return 'WATCH', YELLOW
    return 'CLEAR', GREEN

def draw_sensor_row(label, mm, x, y, w, live=True, max_mm=2000):
    word, col = sensor_word(mm, live)
    pygame.draw.rect(screen, (8, 18, 30), (x, y, w, 24), border_radius=4)
    pygame.draw.rect(screen, col, (x, y, w, 24), 1, border_radius=4)
    blit_fit(label, F10, DIM, x+5, y+3, 42)
    blit_fit(word, F13, col, x+48, y+2, 58)
    txt = f'{int(mm)} mm' if live and mm is not None and mm >= 0 else '---'
    blit_fit(txt, F13, WHITE if live else RED, x+w-66, y+2, 60)
    bx = x + 108
    bw = max(20, w - 180)
    pct = 0 if not live or mm is None or mm < 0 else max(0, min(100, (mm / max_mm) * 100))
    draw_bar(bx, y+8, bw, 7, pct, col)

def draw_distance_tile(label, mm, x, y, w, h, live=True):
    draw_sensor_row(label, mm, x, y, w, live)

def draw_ultrasonic_map(x, y, w, h):
    front = DATA.get('us_front', -1.0)
    left = DATA.get('us_left', -1.0)
    right = DATA.get('us_right', -1.0)
    live = fresh('us_status', 2.5) or fresh('us_front', 2.5) or fresh('us_left', 2.5) or fresh('us_right', 2.5)
    valid = [v for v in [front, left, right] if v is not None and v >= 0]
    nearest = min(valid) if valid else -1
    zone, zc = sensor_word(nearest, live and nearest >= 0)

    pygame.draw.rect(screen, (5, 12, 22), (x, y, w, h), border_radius=6)
    pygame.draw.rect(screen, zc if live else RED, (x, y, w, h), 2, border_radius=6)
    blit_fit(f'ULTRASONIC {zone}', F15, zc, x+7, y+4, w-14)
    nearest_txt = f'nearest {int(nearest)} mm' if nearest >= 0 else 'no distance data'
    blit_fit(nearest_txt, F10, DIM, x+7, y+24, w-14)
    ry = y + 39
    draw_sensor_row('FRONT', front, x+7, ry, w-14, live, 1800)
    draw_sensor_row('LEFT', left, x+7, ry+27, w-14, live, 1800)
    draw_sensor_row('RIGHT', right, x+7, ry+54, w-14, live, 1800)
def draw_compass(cx, cy, r, deg):
    deg = deg % 360.0
    pygame.draw.circle(screen, (5, 15, 26), (cx, cy), r)
    pygame.draw.circle(screen, (0, 195, 255), (cx, cy), r, 2)
    pygame.draw.circle(screen, (16, 42, 66), (cx, cy), r-15, 1)
    for ang in range(0, 360, 30):
        rad = math.radians(ang - 90)
        outer = (cx + int((r-4)*math.cos(rad)), cy + int((r-4)*math.sin(rad)))
        inner_len = 13 if ang % 90 == 0 else 8
        inner = (cx + int((r-inner_len)*math.cos(rad)), cy + int((r-inner_len)*math.sin(rad)))
        pygame.draw.line(screen, (90, 155, 200), outer, inner, 1)
    for lbl, ang, col in [('N',0,RED),('E',90,WHITE),('S',180,WHITE),('W',270,WHITE)]:
        rad = math.radians(ang - 90)
        lx = cx + int((r-24)*math.cos(rad))
        ly = cy + int((r-24)*math.sin(rad))
        s = F13.render(lbl, True, col)
        screen.blit(s, (lx - s.get_width()//2, ly - s.get_height()//2))
    rad = math.radians(deg - 90)
    tip = (cx + int((r-17)*math.cos(rad)), cy + int((r-17)*math.sin(rad)))
    tail = (cx + int(20*math.cos(rad+math.pi)), cy + int(20*math.sin(rad+math.pi)))
    left = (cx + int(10*math.cos(rad+2.55)), cy + int(10*math.sin(rad+2.55)))
    right = (cx + int(10*math.cos(rad-2.55)), cy + int(10*math.sin(rad-2.55)))
    pygame.draw.polygon(screen, RED, [tip, left, tail, right])
    pygame.draw.line(screen, (0, 230, 255), tail, tip, 2)
    pygame.draw.circle(screen, WHITE, (cx, cy), 4)

def hline(x1, y, x2, c=BORDER): pygame.draw.line(screen, c, (x1,y), (x2,y), 1)
def vline(x, y1, y2, c=BORDER): pygame.draw.line(screen, c, (x,y1), (x,y2), 1)

# ?????? Cached state ???????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
_ip    = ip_addr()
_net   = net_status()
_ip_ts = time.monotonic()

# ????????????????????????????????????????????????????????????????????????????????? MAIN LOOP ????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
# ========== SPLASH SCREEN ==========
_splash_logo = scaled_logo(int(W * 0.55), int(H * 0.62))
for _spi in range(101):
    for _e in pygame.event.get():
        if _e.type == pygame.QUIT:
            pygame.quit()
            import sys; sys.exit()
    screen.fill((0, 4, 12))
    if _splash_logo:
        _pulse = 1.0 + 0.012 * math.sin(_spi / 8.0)
        _lw, _lh = _splash_logo.get_size()
        _logo = pygame.transform.smoothscale(_splash_logo, (int(_lw * _pulse), int(_lh * _pulse)))
        screen.blit(_logo, (W//2 - _logo.get_width()//2, int(H*0.40) - _logo.get_height()//2))
    else:
        _st2 = F22.render("PROJECT ATLAS", True, (0, 220, 255))
        screen.blit(_st2, (W//2-_st2.get_width()//2, int(H*0.43)))
    _scan_x = 252 + int(520 * (_spi / 100.0))
    pygame.draw.line(screen, (0, 55, 80), (252, 415), (772, 415), 2)
    pygame.draw.line(screen, (0, 210, 255), (252, 415), (_scan_x, 415), 3)
    pygame.draw.circle(screen, GREEN, (_scan_x, 415), 6)
    pygame.draw.rect(screen, (12, 22, 38), (262, 428, 500, 14))
    pygame.draw.rect(screen, (0, 80, 120), (262, 428, 500, 14), 1)
    if _spi > 0:
        pygame.draw.rect(screen, (0, 180, 255), (263, 429, int(498*_spi/100), 12))
    _lbls = ["Initializing ROS2...","Loading sensors...","Connecting radar...","Ready."]
    _slt = F13.render(_lbls[min(_spi//25,3)], True, (0, 110, 155))
    screen.blit(_slt, (W//2-_slt.get_width()//2, int(H*0.76)))
    pygame.display.flip()
    pygame.time.wait(25)
# ========== END SPLASH ==========

def clip_text(text, font, max_w):
    text = str(text)
    if font.size(text)[0] <= max_w:
        return text
    ell = '..'
    while text and font.size(text + ell)[0] > max_w:
        text = text[:-1]
    return text + ell

def blit_fit(text, font, color, x, y, max_w):
    screen.blit(font.render(clip_text(text, font, max_w), True, color), (x, y))

def panel_rect(x, y, w, h, title, color=ACCENT):
    pygame.draw.rect(screen, PANEL, (x, y, w, h), border_radius=6)
    pygame.draw.rect(screen, BORDER, (x, y, w, h), 1, border_radius=6)
    pygame.draw.rect(screen, HDR, (x, y, w, 24), border_radius=6)
    pygame.draw.line(screen, color, (x, y+24), (x+w, y+24), 1)
    blit_fit(title, F15, color, x+8, y+4, w-16)
    return y + 30

def kv(x, y, label, value, value_color=WHITE, w=170, lf=F10, vf=F13):
    blit_fit(label, lf, DIM, x, y, w)
    blit_fit(value, vf, value_color, x, y+12, w)
    return y + 32

def mini_status(x, y, label, ok, note='', w=70):
    col = GREEN if ok else RED
    pygame.draw.circle(screen, col, (x+6, y+8), 5)
    blit_fit(label, F10, WHITE, x+15, y+1, w-15)
    if note:
        blit_fit(note, F10, DIM, x+15, y+13, w-15)

def draw_power_block(x, y, w, h):
    cy = panel_rect(x, y, w, h, 'BMS POWER', ACCENT)
    bms_ok = fresh('bms_status', 15.0) and fresh('bms_voltage', 15.0)
    bms_pct = DATA.get('bms_pct', 0.0) or 0.0
    bms_v = DATA.get('bms_voltage', 0.0) or 0.0
    bms_i = DATA.get('bms_current', 0.0) or 0.0
    bms_w = DATA.get('bms_power', 0.0) or (bms_v * bms_i)
    bms_c = GREEN if bms_pct > 30 else (YELLOW if bms_pct > 15 else RED)

    draw_bar(x+10, cy, w-20, 15, bms_pct if bms_ok else 0, bms_c if bms_ok else RED)
    blit_fit(f'MAIN BATTERY {bms_pct:.0f}%  {bms_v:.2f}V' if bms_ok else 'MAIN BATTERY  DALY BMS WAITING',
             F13, WHITE if bms_ok else YELLOW, x+14, cy+1, w-28)
    cy += 32
    blit_fit('LIVE BMS LOAD', F10, DIM, x+12, cy, 110)
    blit_fit(f'{abs(bms_w):.1f} W', F22, GREEN if bms_ok else RED, x+12, cy+14, w-24)
    cy += 54
    blit_fit(f'{bms_v:.2f} V', F18, WHITE if bms_ok else RED, x+12, cy, (w-32)//2)
    blit_fit(f'{bms_i:+.2f} A', F18, WHITE if bms_ok else RED, x+w//2, cy, (w-32)//2)

    bc1 = DATA.get('bms_cell1', 0.0) or 0.0
    bc2 = DATA.get('bms_cell2', 0.0) or 0.0
    bc3 = DATA.get('bms_cell3', 0.0) or 0.0
    bc4 = DATA.get('bms_cell4', 0.0) or 0.0

    detail_y = y + h - 34
    pygame.draw.line(screen, BORDER, (x+10, detail_y-7), (x+w-10, detail_y-7), 1)
    cell_w = (w - 32) // 4
    for idx, val in enumerate([bc1, bc2, bc3, bc4], start=1):
        bx = x + 10 + (idx - 1) * (cell_w + 4)
        pygame.draw.rect(screen, (5, 24, 38), (bx, detail_y, cell_w, 27), border_radius=4)
        pygame.draw.rect(screen, BORDER, (bx, detail_y, cell_w, 27), 1, border_radius=4)
        blit_fit(f'C{idx}', F10, ACCENT, bx+5, detail_y+2, 22)
        txt = f'{val:.3f}V' if bms_ok else '--V'
        blit_fit(txt, F13, WHITE if bms_ok else YELLOW, bx+28, detail_y+7, cell_w-32)

def draw_attitude_block(x, y, w, h):
    cy = panel_rect(x, y, w, h, 'ATTITUDE / ODOM', ACCENT)
    heading = DATA.get('heading', DATA.get('yb_heading', 0.0)) or 0.0
    draw_compass(x+58, cy+55, 42, heading)
    hs = F15.render(f'{heading:05.1f} deg', True, ACCENT)
    screen.blit(hs, (x+58-hs.get_width()//2, cy+104))
    rx = x + 112
    ry = cy + 2
    roll = DATA.get('roll', DATA.get('yb_roll', 0.0)) or 0.0
    pitch = DATA.get('pitch', DATA.get('yb_pitch', 0.0)) or 0.0
    yaw = DATA.get('yaw', heading) or 0.0
    pos_x = DATA.get('pos_x', 0.0) or 0.0
    pos_y = DATA.get('pos_y', 0.0) or 0.0
    for label, value in [('ROLL', roll), ('PITCH', pitch), ('YAW', yaw)]:
        blit_fit(f'{label} {value:+.1f}deg', F13, WHITE, rx, ry, w-122)
        ry += 22
    blit_fit(f'ODOM {pos_x:+.2f}m {pos_y:+.2f}m', F13, ACCENT, rx, ry, w-122)

def draw_camera_block(x, y, w, h):
    global _detect_frame
    pygame.draw.rect(screen, (0, 0, 0), (x, y, w, h), border_radius=6)
    pygame.draw.rect(screen, BORDER, (x, y, w, h), 1, border_radius=6)
    cam_frame = None
    with _dash_node._cam_lock:
        if _dash_node._cam_frame is not None:
            cam_frame = _dash_node._cam_frame.copy()
    if cam_frame is not None:
        frame = cv2.resize(cam_frame, (w, h))
        if ENABLE_YOLO and AI_ACTIVE:
            with _detect_frame_lk:
                _detect_frame = cam_frame.copy()
        screen.blit(pygame.surfarray.make_surface(np.rot90(frame)), (x, y))
        if ENABLE_YOLO and AI_ACTIVE:
            with _detect_lock:
                detections = list(_detect_results)
                source_w, source_h = _detect_result_size
            for x1, y1, x2, y2, label, confidence in detections:
                dx1, dy1 = int(x1*w/max(1,source_w)), int(y1*h/max(1,source_h))
                dx2, dy2 = int(x2*w/max(1,source_w)), int(y2*h/max(1,source_h))
                box = pygame.Rect(x+dx1, y+dy1, max(1, dx2-dx1), max(1, dy2-dy1))
                pygame.draw.rect(screen, GREEN, box, 2)
                tag = f'{label.upper()} {confidence*100:.0f}%'
                tw = min(180, max(80, len(tag)*8))
                pygame.draw.rect(screen, (0, 20, 12), (x+dx1, max(y, y+dy1-20), tw, 20))
                blit_fit(tag, F10, GREEN, x+dx1+4, max(y+2, y+dy1-18), tw-8)
            hud_label(f'AI {len(detections)} OBJECTS', x+125, y+8,
                      GREEN if _detect_model is not None else YELLOW, F10, 150)
        elif ENABLE_YOLO:
            hud_label('AI ECO / OFF', x+125, y+8, YELLOW, F10, 150)
        blit_fit('CAMERA LIVE', F13, GREEN, x+10, y+8, 110)
    else:
        pygame.draw.rect(screen, (12, 15, 22), (x, y, w, h), border_radius=6)
        msg = F22.render('NO CAMERA SIGNAL', True, RED)
        screen.blit(msg, (x+w//2-msg.get_width()//2, y+h//2-18))
        blit_fit('/camera/image_raw has no frame', F13, DIM, x+16, y+h//2+12, w-32)
    if ATLAS_LOGO:
        logo = scaled_logo(58, 50)
        if logo:
            screen.blit(logo, (x+w-70, y+8))

def draw_radar_block(x, y, w, h):
    cy = panel_rect(x, y, w, h, 'RADAR', ORANGE)
    raw = DATA.get('radar', '')
    targets = parse_radar_targets(raw)
    live = fresh('radar', 2.0)
    blit_fit(f'TARGETS {len(targets)}', F15, GREEN if live else RED, x+10, cy, 100)
    blit_fit('LIVE' if live else 'NO DATA', F13, GREEN if live else RED, x+w-70, cy+2, 60)
    draw_radar_ppi(x+w//2, y+126, 72, targets, time.time())
    if targets:
        nearest = min(targets, key=lambda t: t['dist'])
        zone = 'CLEAR' if nearest['dist'] > 800 else 'CAUTION'
        col = GREEN if zone == 'CLEAR' else RED
        blit_fit(zone, F18, col, x+10, y+h-54, w-20)
        blit_fit(f'X {nearest["x"]:+d}mm   Y {nearest["y"]}mm   SPD {nearest["speed"]:+d}cm/s', F13, WHITE, x+10, y+h-28, w-20)
    else:
        blit_fit('No radar target text', F13, DIM, x+10, y+h-36, w-20)

def draw_motors_block(x, y, w, h):
    cy = panel_rect(x, y, w, h, 'MOTORS / STEERING', GREEN)
    vals = [
        ('FL', DATA.get('fl', 0.0) or 0.0),
        ('FR', DATA.get('fr', 0.0) or 0.0),
        ('BL', DATA.get('rl', 0.0) or 0.0),
        ('BR', DATA.get('rr', 0.0) or 0.0),
    ]
    for label, val in vals:
        blit_fit(label, F10, DIM, x+10, cy+4, 22)
        draw_bar(x+36, cy, w-84, 16, min(abs(val), 100), GREEN if abs(val) > 1 else DIM)
        blit_fit(f'{val:+.0f}%', F10, WHITE, x+w-42, cy+3, 36)
        cy += 22

    fs = DATA.get('front_steer', 0.0) or 0.0
    rs = DATA.get('rear_steer', 0.0) or 0.0
    cmd = DATA.get('steering', 0.0) or 0.0
    mode = DATA.get('steer_mode', '--') or '--'
    steer_live = fresh('front_steer', 2.0) or fresh('rear_steer', 2.0)
    pygame.draw.rect(screen, (8, 18, 30), (x+8, cy, w-16, 48), border_radius=5)
    pygame.draw.rect(screen, (28, 58, 82), (x+8, cy, w-16, 48), 1, border_radius=5)
    blit_fit('STEERING', F10, ACCENT, x+14, cy+5, 70)
    blit_fit(f'F {fs:.0f}  R {rs:.0f} deg', F13, GREEN if steer_live else RED, x+86, cy+3, w-100)
    blit_fit(f'CMD {cmd:+.1f}   {mode}', F10, DIM, x+14, cy+27, w-28)
    cy += 58

    enc = DATA.get('enc_speed', None)
    blit_fit('ENC SPD', F10, DIM, x+10, cy, 62)
    blit_fit(f'{enc:.3f} m/s' if enc is not None else 'N/A', F13, GREEN if enc is not None else RED, x+72, cy-2, w-82)

def draw_range_block(x, y, w, h):
    cy = panel_rect(x, y, w, h, 'RANGE SENSORS', GREEN)
    front = DATA.get('us_front', -1.0)
    left = DATA.get('us_left', -1.0)
    right = DATA.get('us_right', -1.0)
    us_live = fresh('us_status', 2.5) or fresh('us_front', 2.5) or fresh('us_left', 2.5) or fresh('us_right', 2.5)
    us_vals = [v for v in [front, left, right] if v is not None and v >= 0]
    us_near = min(us_vals) if us_vals else -1
    us_word, us_col = sensor_word(us_near, us_live and us_near >= 0)

    lidar_live = fresh('scan_pts', 2.0)
    pts = DATA.get('scan_pts', 0) or 0
    lmin = DATA.get('lidar_min', -1.0)
    lf = DATA.get('lidar_front', -1.0)
    ll = DATA.get('lidar_left', -1.0)
    lr = DATA.get('lidar_right', -1.0)
    lword, lcol = sensor_word(lmin, lidar_live and lmin >= 0)

    inner_x, inner_y = x + 10, cy
    inner_w, inner_h = w - 20, y + h - cy - 8

    if inner_w >= 290 and inner_h >= 175:
        gap = 8
        card_w = (inner_w - gap) // 2
        card_h = inner_h
        ux, lx = inner_x, inner_x + card_w + gap

        pygame.draw.rect(screen, (5, 12, 22), (ux, inner_y, card_w, card_h), border_radius=6)
        pygame.draw.rect(screen, us_col if us_live else RED, (ux, inner_y, card_w, card_h), 2, border_radius=6)
        blit_fit(f'ULTRA {us_word}', F15, us_col, ux+8, inner_y+5, card_w-16)
        blit_fit(f'near {int(us_near)} mm' if us_near >= 0 else 'no data', F10, DIM, ux+8, inner_y+25, card_w-16)
        cx, ry = ux + card_w//2, inner_y + 88
        pygame.draw.rect(screen, (18, 30, 42), (cx-24, ry-16, 48, 32), border_radius=6)
        pygame.draw.rect(screen, ACCENT, (cx-24, ry-16, 48, 32), 1, border_radius=6)
        pygame.draw.polygon(screen, ACCENT, [(cx, ry-34), (cx-12, ry-16), (cx+12, ry-16)])
        for wx, wy in [(cx-33, ry-15), (cx+33, ry-15), (cx-33, ry+17), (cx+33, ry+17)]:
            pygame.draw.circle(screen, (10, 16, 24), (wx, wy), 5)
            pygame.draw.circle(screen, ACCENT, (wx, wy), 5, 1)
        for label, mm, px, py in [('F', front, cx, inner_y+48), ('L', left, ux+18, ry+23), ('R', right, ux+card_w-58, ry+23)]:
            word, col = sensor_word(mm, us_live)
            pygame.draw.rect(screen, (8, 18, 30), (px-22, py, 44, 30), border_radius=5)
            pygame.draw.rect(screen, col, (px-22, py, 44, 30), 1, border_radius=5)
            blit_fit(label, F10, DIM, px-18, py+2, 12)
            blit_fit(f'{int(mm)}' if us_live and mm is not None and mm >= 0 else '--', F10, col, px-4, py+14, 38)

        pygame.draw.rect(screen, (5, 12, 22), (lx, inner_y, card_w, card_h), border_radius=6)
        pygame.draw.rect(screen, lcol if lidar_live else RED, (lx, inner_y, card_w, card_h), 2, border_radius=6)
        blit_fit(f'LIDAR {lword}', F15, lcol, lx+8, inner_y+5, card_w-16)
        blit_fit(f'near {int(lmin)} mm' if lidar_live and lmin >= 0 else 'no scan', F10, WHITE if lidar_live else RED, lx+8, inner_y+25, card_w-16)
        ox, oy = lx + card_w//2, inner_y + card_h - 18
        max_r = min(card_w//2 - 14, card_h - 68)
        for rr, col in [(max_r, GREEN), (int(max_r*0.68), YELLOW), (int(max_r*0.36), RED)]:
            pygame.draw.arc(screen, col, (ox-rr, oy-rr, rr*2, rr*2), math.radians(200), math.radians(340), 1)
        for ang in [220, 270, 320]:
            rad = math.radians(ang)
            pygame.draw.line(screen, (35, 80, 110), (ox, oy), (ox+int(max_r*math.cos(rad)), oy+int(max_r*math.sin(rad))), 1)
        for label, mm, px in [('L', ll, lx+16), ('F', lf, lx+card_w//2-18), ('R', lr, lx+card_w-52)]:
            word, col = sensor_word(mm, lidar_live)
            pygame.draw.rect(screen, (8, 18, 30), (px, inner_y+48, 36, 28), border_radius=4)
            pygame.draw.rect(screen, col, (px, inner_y+48, 36, 28), 1, border_radius=4)
            blit_fit(label, F10, DIM, px+4, inner_y+50, 10)
            blit_fit(f'{int(mm)}' if lidar_live and mm is not None and mm >= 0 else '--', F10, col, px+4, inner_y+62, 30)
        blit_fit(f'{int(pts)} pts', F10, DIM, lx+8, inner_y+card_h-15, card_w-16)
        return

    available = max(120, inner_h)
    ultra_h = min(120, max(92, int(available * 0.56)))
    draw_ultrasonic_map(inner_x, cy, inner_w, ultra_h)
    cy += ultra_h + 7
    lh = max(48, y + h - cy - 6)
    pygame.draw.rect(screen, (5, 12, 22), (x+10, cy, w-20, lh), border_radius=6)
    pygame.draw.rect(screen, lcol if lidar_live else RED, (x+10, cy, w-20, lh), 2, border_radius=6)
    blit_fit(f'LIDAR {lword}', F15, lcol, x+17, cy+4, w-34)
    blit_fit(f'near {int(lmin)} mm' if lidar_live and lmin >= 0 else 'NO LASER SCAN', F10, WHITE if lidar_live else RED, x+17, cy+24, w-34)
    row_y = cy + lh - 25
    gap = 5
    tw = (w - 34 - gap * 2) // 3
    for i, (label, mm) in enumerate([('F', lf), ('L', ll), ('R', lr)]):
        word, col = sensor_word(mm, lidar_live)
        bx = x + 17 + i * (tw + gap)
        pygame.draw.rect(screen, (8, 18, 30), (bx, row_y, tw, 20), border_radius=4)
        pygame.draw.rect(screen, col, (bx, row_y, tw, 20), 1, border_radius=4)
        txt = f'{label} {int(mm)}' if lidar_live and mm is not None and mm >= 0 else f'{label} --'
        blit_fit(txt, F10, col, bx+3, row_y+4, tw-6)
    blit_fit(f'{int(pts)} pts', F10, DIM, x+w-56, y+h-14, 48)
def draw_comms_block(x, y, w, h):
    cy = panel_rect(x, y, w, h, 'LINK / GPS / SYSTEM', ACCENT)
    global _ip_ts, _ip, _net
    if time.monotonic() - _ip_ts > 10:
        _ip = ip_addr()
        _net = net_status()
        _ip_ts = time.monotonic()

    wifi_ok = _net.get('wifi_ip') == '192.168.1.14'
    cell_ip = _net.get('cell_ip', '--')
    ts_ip = _net.get('ts_ip', '--')
    sig = DATA.get('cell_signal', 0.0) or 0.0
    cell_ok = fresh('cell_signal', 12.0) and sig > 0
    tech = (DATA.get('cell_tech', '--') or '--').upper()
    oper = DATA.get('cell_operator', '') or ''

    ram = psutil.virtual_memory()
    cores = psutil.cpu_percent(percpu=True)
    avg_cpu = sum(cores) / max(len(cores), 1)
    temp = cpu_temp()

    sats = DATA.get('gps_sats', 0.0) or 0.0
    gps_status = DATA.get('gps_status', -1)
    hdop = DATA.get('gps_hdop', 0.0) or 0.0
    counts = parse_constellations(DATA.get('gps_const', ''))
    gps_live = fresh('gps_sats', 12.0) or fresh('gps_status', 12.0) or fresh('gps_const', 12.0)
    gps_fix = gps_live and gps_status is not None and gps_status >= 0
    gcol = GREEN if gps_fix else (YELLOW if gps_live else RED)

    gap = 8
    box_y = cy
    box_h = max(88, y + h - cy - 8)
    box_w = (w - 20 - gap * 3) // 4
    boxes = [x + 10 + i * (box_w + gap) for i in range(4)]

    def box(ix, title, col):
        bx = boxes[ix]
        pygame.draw.rect(screen, (5, 12, 22), (bx, box_y, box_w, box_h), border_radius=6)
        pygame.draw.rect(screen, col, (bx, box_y, box_w, box_h), 1, border_radius=6)
        blit_fit(title, F13, col, bx+8, box_y+6, box_w-16)
        return bx, box_y + 28

    bx, ty = box(0, 'NETWORK', GREEN if wifi_ok or ts_ip != '--' else RED)
    blit_fit('WIFI', F10, DIM, bx+8, ty, 42)
    blit_fit(_net.get('wifi_ip', '--'), F13, GREEN if wifi_ok else RED, bx+54, ty-2, box_w-62)
    ty += 23
    blit_fit('TAIL', F10, DIM, bx+8, ty, 42)
    blit_fit(ts_ip, F13, GREEN if ts_ip != '--' else RED, bx+54, ty-2, box_w-62)
    ty += 23
    blit_fit(_net.get('ssh', '--'), F10, ACCENT, bx+8, ty, box_w-16)

    bx, ty = box(1, 'CELLULAR', GREEN if cell_ok else RED)
    draw_signal_bars(bx+8, ty+2, sig, cell_ok)
    blit_fit(f'{sig:.0f}%', F22, GREEN if cell_ok else RED, bx+64, ty-2, 70)
    blit_fit(tech, F13, WHITE if cell_ok else RED, bx+132, ty+4, box_w-140)
    ty += 33
    blit_fit(cell_ip, F13, GREEN if cell_ip != '--' else RED, bx+8, ty, box_w-16)
    ty += 22
    blit_fit(oper or 'operator --', F10, DIM, bx+8, ty, box_w-16)

    bx, ty = box(2, 'SYSTEM LOAD', YELLOW if avg_cpu >= 70 else GREEN)
    blit_fit(f'CPU {avg_cpu:.0f}%', F18, WHITE, bx+8, ty-3, 90)
    blit_fit(temp, F13, ACCENT, bx+104, ty+1, box_w-112)
    ty += 25
    draw_bar(bx+8, ty, box_w-16, 10, avg_cpu, GREEN if avg_cpu < 60 else (YELLOW if avg_cpu < 80 else RED))
    ty += 20
    blit_fit(f'RAM {ram.percent:.0f}%', F18, WHITE, bx+8, ty-3, 90)
    draw_bar(bx+104, ty+3, box_w-112, 10, ram.percent, GREEN if ram.percent < 70 else YELLOW)

    bx, ty = box(3, 'GPS / GNSS', gcol)
    blit_fit('FIX' if gps_fix else ('SEARCH' if gps_live else 'NO DATA'), F18, gcol, bx+8, ty-3, 90)
    blit_fit(f'{int(sats)} SAT', F22, gcol, bx+102, ty-6, box_w-110)
    ty += 27
    blit_fit(f'HDOP {hdop:.1f}' if hdop > 0 else 'HDOP --', F13, WHITE if gps_live else RED, bx+8, ty, 90)
    ty += 23
    draw_constellation_bars(bx+8, ty-2, counts, gps_live)

def hud_line(x1, y1, x2, y2, color=BORDER, width=1):
    pygame.draw.line(screen, color, (int(x1), int(y1)), (int(x2), int(y2)), width)

def hud_label(text, x, y, color=ACCENT, font=F13, w=160):
    blit_fit(text, font, color, int(x), int(y), int(w))

def jetson_input_power():
    try:
        base = '/sys/class/hwmon/hwmon1'
        voltage = float(open(base + '/in1_input').read()) / 1000.0
        current = float(open(base + '/curr1_input').read()) / 1000.0
        return voltage, current, voltage * current
    except Exception:
        return 0.0, 0.0, 0.0

def draw_hud_power(x, y, w, h):
    global POWER_IDLE_BASELINE
    hud_label('POWER DISTRIBUTION', x, y, ACCENT, F18, w)
    hud_line(x, y+26, x+w, y+26, ACCENT, 1)
    bms_ok = fresh('bms_status', 15.0) and fresh('bms_voltage', 15.0)
    bms_pct = DATA.get('bms_pct', 0.0) or 0.0
    bms_v = DATA.get('bms_voltage', 0.0) or 0.0
    bms_i = DATA.get('bms_current', 0.0) or 0.0
    bms_w = DATA.get('bms_power', 0.0) or (bms_v * bms_i)
    col = GREEN if bms_ok and bms_pct > 30 else (YELLOW if bms_ok and bms_pct > 10 else RED)
    ry = y + 46
    hud_label('MAIN BATTERY', x, ry, col, F15, 118)
    hud_label(f'{bms_pct:.0f}%', x+124, ry-4, WHITE if bms_ok else RED, F22, w-128)
    draw_bar(x, ry+32, w, 12, bms_pct if bms_ok else 0, col)
    ry += 66
    hud_label('LIVE LOAD', x, ry+7, DIM, F10, 78)
    hud_label(f'{abs(bms_w):.1f} W', x+84, ry, GREEN if bms_ok else RED, F22, w-88)
    ry += 38
    hud_label(f'{bms_v:.2f} V', x, ry, WHITE if bms_ok else RED, F18, w//2)
    hud_label(f'{bms_i:+.2f} A', x+w//2, ry, WHITE if bms_ok else RED, F18, w//2)

    card_y = y + 204
    card_gap = 12
    card_w = (w - card_gap) // 2
    jetson_v, jetson_i, jetson_w = jetson_input_power()
    jetson_ok = jetson_v > 1.0 and jetson_i >= 0.0
    motor_v = DATA.get('voltage', 0.0) or 0.0
    motor_i = DATA.get('current', 0.0) or 0.0
    motor_live = fresh('voltage', 3.0) and motor_v > 1.0
    motor_current_live = fresh('current', 3.0) and abs(motor_i) > 0.001
    command_active = (
        fresh('cmd_lin', 1.0) and
        (abs(DATA.get('cmd_lin', 0.0) or 0.0) > 0.02 or
         abs(DATA.get('cmd_ang', 0.0) or 0.0) > 0.02)
    )
    total_w = abs(float(bms_w))
    if bms_ok and total_w > 1.0 and not command_active:
        if POWER_IDLE_BASELINE is None:
            POWER_IDLE_BASELINE = total_w
        else:
            POWER_IDLE_BASELINE = POWER_IDLE_BASELINE*0.98 + total_w*0.02
    estimated_motor_w = max(0.0, total_w-(POWER_IDLE_BASELINE or total_w))

    pygame.draw.rect(screen, (8, 20, 32), (x, card_y, card_w, 54), border_radius=5)
    pygame.draw.rect(screen, GREEN if jetson_ok else RED, (x, card_y, card_w, 54), 1, border_radius=5)
    hud_label('JETSON INPUT', x+8, card_y+5, GREEN if jetson_ok else RED, F10, card_w-16)
    hud_label(
        f'{jetson_w:.1f}W  {jetson_v:.2f}V  {jetson_i:.2f}A' if jetson_ok else 'POWER SENSOR OFFLINE',
        x+8, card_y+24, WHITE if jetson_ok else RED, F13, card_w-16
    )

    motor_x = x + card_w + card_gap
    pygame.draw.rect(screen, (8, 20, 32), (motor_x, card_y, card_w, 54), border_radius=5)
    pygame.draw.rect(screen, YELLOW if motor_live else RED, (motor_x, card_y, card_w, 54), 1, border_radius=5)
    hud_label('MOTOR BOARD', motor_x+8, card_y+5, YELLOW if motor_live else RED, F10, card_w-16)
    if motor_live and motor_current_live:
        motor_text = f'{abs(motor_v * motor_i):.1f}W  {motor_v:.2f}V  {motor_i:+.2f}A'
    elif motor_live:
        motor_text = f'EST ~{estimated_motor_w:.1f}W  {motor_v:.2f}V  BMS-IDLE'
    else:
        motor_text = 'TELEMETRY OFFLINE'
    hud_label(motor_text, motor_x+8, card_y+24, WHITE if motor_live else RED, F13, card_w-16)

    cells = [DATA.get(f'bms_cell{i}', 0.0) or 0.0 for i in range(1,5)]
    cy = y + h - 24
    cw = w // 4
    for i, val in enumerate(cells, 1):
        hud_label(f'C{i} {val:.3f}' if bms_ok else f'C{i} --', x+(i-1)*cw, cy, WHITE if bms_ok else YELLOW, F10, cw-4)

def thermal_color(v, mn, mx):
    if mx <= mn:
        mx = mn + 1.0
    t = max(0.0, min(1.0, (float(v) - mn) / (mx - mn)))
    if t < 0.5:
        k = t * 2.0
        return (int(20 + 40*k), int(70 + 130*k), int(180 + 45*k))
    k = (t - 0.5) * 2.0
    return (int(80 + 175*k), int(200 - 80*k), int(225 - 210*k))

def draw_thermal_grid(x, y, w, h):
    d = DATA.get('thermal_json', {}) or {}
    pix = d.get('pixels', []) if isinstance(d, dict) else []
    live = fresh('thermal_json', 3.0) and len(pix) == 64 and bool(d.get('ok'))
    mn = float(d.get('min_c', 0.0) or 0.0) if isinstance(d, dict) else 0.0
    mx = float(d.get('max_c', 0.0) or 0.0) if isinstance(d, dict) else 0.0
    avg = float(d.get('avg_c', 0.0) or 0.0) if isinstance(d, dict) else 0.0
    cen = float(d.get('center_c', 0.0) or 0.0) if isinstance(d, dict) else 0.0
    status = DATA.get('thermal_status', 'AMG8833 OFFLINE') or 'AMG8833 OFFLINE'
    col = ORANGE if live else RED
    hud_label('THERMAL IR', x, y, col, F15, w)
    hud_label(f'{mn:.1f}-{mx:.1f}C  avg {avg:.1f}C' if live else status[:30], x, y+22, WHITE if live else RED, F10, w)

    gx, gy = x, y + 48
    grid = max(64, min(w - 12, int((h - 100) * 0.58)))
    cell = max(6, grid // 8)
    grid = cell * 8
    hot_i = max(range(64), key=lambda i: pix[i]) if live else -1
    cold_i = min(range(64), key=lambda i: pix[i]) if live else -1
    for rr in range(8):
        for cc in range(8):
            idx = rr * 8 + cc
            px, py = gx + cc * cell, gy + rr * cell
            fill = thermal_color(pix[idx], mn, mx) if live else (18, 24, 34)
            pygame.draw.rect(screen, fill, (px, py, cell - 1, cell - 1))
            if idx == hot_i:
                pygame.draw.rect(screen, WHITE, (px + 1, py + 1, cell - 3, cell - 3), 2)
            elif idx == cold_i:
                pygame.draw.rect(screen, ACCENT, (px + 1, py + 1, cell - 3, cell - 3), 1)
    pygame.draw.rect(screen, col, (gx, gy, grid, grid), 2)

    chart_y = gy + grid + 18
    chart_h = max(34, h - (chart_y - y) - 22)
    pygame.draw.rect(screen, (8, 16, 26), (x, chart_y, w, chart_h))
    pygame.draw.rect(screen, BORDER, (x, chart_y, w, chart_h), 1)
    hud_label('TEMP HISTORY  HIGH / LOW', x+6, chart_y+4, DIM, F10, w-12)
    hist = THERMAL_HISTORY[-60:]
    if len(hist) >= 2:
        vals = [v for _, lo, hi, _ in hist for v in (lo, hi)]
        lo_v, hi_v = min(vals), max(vals)
        if hi_v <= lo_v:
            hi_v = lo_v + 1.0
        def pt(i, v):
            px = x + 8 + int(i * (w - 16) / max(1, len(hist) - 1))
            py = chart_y + chart_h - 8 - int((v - lo_v) * (chart_h - 24) / (hi_v - lo_v))
            return px, py
        high_pts = [pt(i, row[2]) for i, row in enumerate(hist)]
        low_pts = [pt(i, row[1]) for i, row in enumerate(hist)]
        if len(high_pts) > 1:
            pygame.draw.lines(screen, ORANGE, False, high_pts, 2)
            pygame.draw.lines(screen, ACCENT, False, low_pts, 2)
        hud_label(f'H {hist[-1][2]:.1f}C', x+8, chart_y+chart_h-18, ORANGE, F10, 70)
        hud_label(f'L {hist[-1][1]:.1f}C', x+78, chart_y+chart_h-18, ACCENT, F10, 70)
    else:
        hud_label('recording...', x+8, chart_y+chart_h//2-6, DIM, F10, w-16)
    hot_txt = f'HOT {mx:.1f}C  CENTER {cen:.1f}C' if live else 'expected I2C 0x69/0x68'
    hud_label(hot_txt, x, y+h-14, col if live else YELLOW, F10, w)

def draw_environment_panel(x, y, w, h):
    d = DATA.get('thermal_json', {}) or {}
    pixels = d.get('pixels', []) if isinstance(d, dict) else []
    inside_live = fresh('thermal_json', 3.0) and len(pixels) == 64 and bool(d.get('ok'))
    inside_min = float(d.get('min_c', 0.0) or 0.0) if isinstance(d, dict) else 0.0
    inside_max = float(d.get('max_c', 0.0) or 0.0) if isinstance(d, dict) else 0.0
    inside_avg = float(d.get('avg_c', 0.0) or 0.0) if isinstance(d, dict) else 0.0
    outside_live = fresh('outside_temperature', 6.0)
    outside_temp = DATA.get('outside_temperature', 0.0) or 0.0
    outside_humidity = DATA.get('outside_humidity', 0.0) or 0.0

    hud_label('TEMPERATURE HISTORY', x, y, GREEN if inside_live and outside_live else YELLOW, F15, w)
    gap = 8
    card_w = (w-gap)//2
    inside_values = [row[3] for row in THERMAL_HISTORY[-120:] if 5.0 <= row[3] <= 60.0]
    outside_values = [value for _, value in AMBIENT_HISTORY[-120:] if 5.0 <= value <= 60.0]

    def temperature_card(card_x, title, current, values, color, live,
                         humidity=None, show_heatmap=False):
        card_y, card_h = y+24, h-24
        pygame.draw.rect(screen, (8, 16, 26), (card_x, card_y, card_w, card_h))
        pygame.draw.rect(screen, color if live else RED, (card_x, card_y, card_w, card_h), 1)
        hud_label(title, card_x+7, card_y+5, color if live else RED, F13, card_w-14)
        hud_label(f'{current:.1f} C' if live else '--.- C', card_x+7, card_y+23,
                  WHITE if live else RED, F18, 100)
        valid = values if values else ([current] if live else [])
        measured_min = min(valid) if valid else 0.0
        measured_max = max(valid) if valid else 0.0
        hud_label(f'MIN {measured_min:.1f} C', card_x+108, card_y+23,
                  ACCENT if live else RED, F10, card_w-112)
        hud_label(f'MAX {measured_max:.1f} C', card_x+108, card_y+39,
                  ORANGE if live else RED, F10, card_w-112)
        if humidity is not None:
            hud_label(f'HUMIDITY {humidity:.0f}%', card_x+7, card_y+44,
                      ACCENT if live else RED, F10, 100)

        chart_x = card_x+76 if show_heatmap else card_x+6
        chart_y = card_y+64
        chart_w = card_w-82 if show_heatmap else card_w-12
        chart_h = card_h-70
        if show_heatmap:
            heat_x, heat_y, heat_cell = card_x+6, card_y+76, 8
            hot_index = max(range(64), key=lambda i: pixels[i]) if inside_live else -1
            for heat_row in range(8):
                for heat_column in range(8):
                    heat_index = heat_row*8+heat_column
                    px = heat_x+heat_column*heat_cell
                    py = heat_y+heat_row*heat_cell
                    fill = thermal_color(pixels[heat_index], inside_min, inside_max) if inside_live else (18,24,34)
                    pygame.draw.rect(screen, fill, (px, py, heat_cell-1, heat_cell-1))
                    if heat_index == hot_index:
                        pygame.draw.rect(screen, WHITE, (px+1, py+1, heat_cell-3, heat_cell-3), 1)
            pygame.draw.rect(screen, ORANGE if inside_live else RED,
                             (heat_x, heat_y, heat_cell*8, heat_cell*8), 1)
            hud_label('8x8 IR MAP', heat_x, heat_y+69, DIM, F10, 66)
            hud_label(f'{inside_min:.1f}-{inside_max:.1f}C' if inside_live else 'OFFLINE',
                      heat_x, heat_y+85, WHITE if inside_live else RED, F10, 66)
        pygame.draw.rect(screen, (5, 11, 19), (chart_x, chart_y, chart_w, chart_h))
        pygame.draw.rect(screen, BORDER, (chart_x, chart_y, chart_w, chart_h), 1)
        if valid:
            low = math.floor((min(valid)-0.5)*2)/2
            high = math.ceil((max(valid)+0.5)*2)/2
            if high-low < 1.5:
                middle = (high+low)/2
                low, high = middle-0.75, middle+0.75
            plot_left, plot_right = chart_x+34, chart_x+chart_w-5
            plot_top, plot_bottom = chart_y+8, chart_y+chart_h-17
            for index in range(3):
                value = high-index*(high-low)/2
                py = int(plot_top+index*(plot_bottom-plot_top)/2)
                hud_line(plot_left, py, plot_right, py, (25, 48, 65), 1)
                hud_label(f'{value:.1f}', chart_x+3, py-6, DIM, F10, 29)
            points = [
                (plot_left+int(index*(plot_right-plot_left)/max(1, len(valid)-1)),
                 plot_bottom-int((value-low)*(plot_bottom-plot_top)/max(0.1, high-low)))
                for index, value in enumerate(valid)
            ]
            if len(points) > 1:
                pygame.draw.lines(screen, color, False, points, 3)
            elif points:
                pygame.draw.circle(screen, color, points[0], 3)
            hud_label('LAST 2 MIN', plot_left, chart_y+chart_h-14, DIM, F10, chart_w-38)
        else:
            hud_label('WAITING FOR SENSOR', chart_x+36, chart_y+chart_h//2,
                      RED, F10, chart_w-42)

    temperature_card(x, 'INSIDE IR SURFACE', inside_avg, inside_values,
                     ORANGE, inside_live, show_heatmap=True)
    temperature_card(x+card_w+gap, 'OUTSIDE AMBIENT', outside_temp,
                     outside_values, ACCENT, outside_live, outside_humidity)

def draw_hud_sensor_strip(x, y, w, h):
    hud_label('SENSOR AWARENESS', x, y, GREEN, F18, 230)
    hud_line(x, y+26, x+w, y+26, GREEN, 1)
    third = w // 4
    ux, lx, rx, tx = x, x + third, x + third * 2, x + third * 3
    hud_line(lx-8, y+36, lx-8, y+h, BORDER, 1)
    hud_line(rx-8, y+36, rx-8, y+h, BORDER, 1)
    hud_line(tx-8, y+36, tx-8, y+h, BORDER, 1)
    us_live = fresh('us_status', 2.5) or fresh('us_front', 2.5)
    left = DATA.get('us_left', -1.0); front = DATA.get('us_front', -1.0); right = DATA.get('us_right', -1.0)
    us_vals = [v for v in [left, front, right] if v is not None and v >= 0]
    us_near = min(us_vals) if us_vals else -1
    us_word, us_col = sensor_word(us_near, us_live and us_near >= 0)
    hud_label(f'ULTRASONIC {us_word}', ux, y+40, us_col, F15, third-20)
    hud_label(f'nearest {int(us_near)}mm' if us_near >= 0 else 'no data', ux, y+62, DIM, F10, third-20)
    cx, cy = ux + third//2 - 10, y + 126

    def beam(label, mm, angle_deg, length, width_deg=24):
        _, col = sensor_word(mm, us_live)
        rad = math.radians(angle_deg)
        spread = math.radians(width_deg)
        p1 = (cx, cy)
        p2 = (cx + int(length * math.cos(rad - spread)), cy + int(length * math.sin(rad - spread)))
        p3 = (cx + int(length * math.cos(rad + spread)), cy + int(length * math.sin(rad + spread)))
        pygame.draw.polygon(screen, (8, 20, 30), [p1, p2, p3])
        pygame.draw.line(screen, col, p1, p2, 2)
        pygame.draw.line(screen, col, p1, p3, 2)
        tx = cx + int((length + 10) * math.cos(rad))
        ty = cy + int((length + 10) * math.sin(rad))
        hud_label(label, tx-22, ty-13, DIM, F10, 42)
        hud_label(f'{int(mm)}' if us_live and mm is not None and mm >= 0 else '--', tx-22, ty, col, F13, 54)

    beam('FRONT', front, -90, 58, 20)
    beam('LEFT', left, 180, 58, 18)
    beam('RIGHT', right, 0, 58, 18)

    logo = scaled_logo(74, 74)
    if logo:
        screen.blit(logo, (cx - logo.get_width()//2, cy - logo.get_height()//2))
    else:
        pygame.draw.circle(screen, (10, 18, 28), (cx, cy), 32)
        pygame.draw.circle(screen, ACCENT, (cx, cy), 32, 2)
        hud_label('ATLAS', cx-26, cy-7, ACCENT, F13, 52)
    lidar_live = fresh('scan_pts', 2.0)
    lmin = DATA.get('lidar_min', -1.0); lf = DATA.get('lidar_front', -1.0); ll = DATA.get('lidar_left', -1.0); lr = DATA.get('lidar_right', -1.0)
    hud_label('LIDAR FAN', lx, y+40, ACCENT, F15, third-20)
    # Keep the fan completely inside the sensor strip.  Its former origin was
    # only 18 px above the divider, so the lower half crossed into MOTION.
    ox, oy = lx + third//2 - 12, y + h - 70
    max_r = min(72, third//2 - 26, h - 108)
    for rr, col in [(max_r, GREEN), (int(max_r*.68), YELLOW), (int(max_r*.36), RED)]:
        pygame.draw.arc(screen, col, (ox-rr, oy-rr, rr*2, rr*2), math.radians(200), math.radians(340), 1)
    for ang in [215, 270, 325]:
        rad = math.radians(ang)
        hud_line(ox, oy, ox + max_r*math.cos(rad), oy + max_r*math.sin(rad), (35,80,110), 1)
    for label, mm, px in [('L', ll, lx+18), ('F', lf, ox-28), ('R', lr, lx+third-92)]:
        _, col = sensor_word(mm, lidar_live)
        hud_label(label, px, y+62, DIM, F10, 16)
        hud_label(f'{int(mm)}mm' if lidar_live and mm is not None and mm >= 0 else '--', px+18, y+60, col, F13, 70)
    hud_label(f'nearest {int(lmin)}mm' if lidar_live and lmin >= 0 else 'NO SCAN', lx+18, y+h-24, WHITE if lidar_live else RED, F13, third-36)
    targets = parse_radar_targets(DATA.get('radar', ''))
    hud_label('RADAR', rx, y+40, ORANGE, F15, third-20)
    draw_radar_ppi(rx + third//2 - 12, y+118, min(76, third//2-28), targets, time.time())
    if targets:
        n = min(targets, key=lambda t: t['dist'])
        hud_label(f'{len(targets)} target  near {n["dist"]:.0f}mm', rx+18, y+h-30, WHITE, F13, third-36)
    else:
        hud_label('NO TARGET', rx+18, y+h-30, DIM, F13, third-36)
    draw_environment_panel(tx+8, y+40, third-24, h-48)

def draw_hud_bottom(x, y, w, h):
    hud_line(x, y, x+w, y, ACCENT, 1)
    gap = 12
    col_w = (w - gap * 3) // 4
    xs = [x + i*(col_w+gap) for i in range(4)]
    motor_live = any(fresh(k, 2.5) for k in ('fl', 'fr', 'rl', 'rr', 'enc_speed'))
    hud_label('ENCODERS', xs[0], y+10, GREEN if motor_live else RED, F15, 110)
    if not motor_live:
        hud_label('BASE TELEMETRY OFFLINE', xs[0]+118, y+12, RED, F10, col_w-118)
    for i, (lab, val) in enumerate([('FL',DATA.get('fl',0) or 0),('FR',DATA.get('fr',0) or 0),('BL',DATA.get('rl',0) or 0),('BR',DATA.get('rr',0) or 0)]):
        yy = y + 36 + i*22
        hud_label(lab, xs[0], yy, DIM, F10, 24)
        draw_bar(xs[0]+30, yy+5, col_w-78, 8, abs(val) if motor_live else 0, GREEN if motor_live and abs(val)>1 else DIM)
        hud_label(f'{val:+.0f}' if motor_live else '--', xs[0]+col_w-40, yy, WHITE if motor_live else RED, F10, 36)
    hud_label('ATTITUDE', xs[1], y+10, ACCENT, F15, col_w)
    compass_key = 'heading' if fresh('heading', 2.5) else 'yb_heading'
    compass_live = fresh(compass_key, 2.5)
    heading = DATA.get(compass_key, 0.0) or 0.0
    hud_label(f'COMPASS {heading:05.1f} deg' if compass_live else 'COMPASS OFFLINE',
              xs[1], y+38, WHITE if compass_live else RED, F15, col_w)
    hud_label(f"X {DATA.get('pos_x',0) or 0:+.2f}m", xs[1], y+66, ACCENT, F13, col_w)
    hud_label(f"Y {DATA.get('pos_y',0) or 0:+.2f}m", xs[1], y+90, ACCENT, F13, col_w)
    hud_label('AP / NETWORK', xs[2], y+10, ACCENT, F15, col_w)
    wifi_ip = _net.get('wifi_ip','--')
    cell_ip = _net.get('cell_ip','--')
    ts_ip = _net.get('ts_ip','--')
    route = (_net.get('route','--') or '--').upper()
    ssh_src = _net.get('ssh','--') or '--'
    if wifi_ip.startswith('192.168.50.') or wifi_ip.startswith('10.42.'):
        wifi_mode, wifi_col, ssid = 'AP MODE', YELLOW, 'ATLAS_ROVER'
    elif wifi_ip != '--':
        wifi_mode, wifi_col, ssid = 'STA MODE', GREEN, _net.get('wifi_ssid', '--')
    else:
        wifi_mode, wifi_col, ssid = 'WIFI OFF', RED, 'NO AP'
    hud_label('WIFI ' + wifi_mode, xs[2], y+34, wifi_col, F15, col_w)
    hud_label('IP ' + wifi_ip, xs[2], y+58, WHITE if wifi_ip != '--' else RED, F13, col_w)
    hud_label('SSID ' + ssid, xs[2], y+80, ACCENT if ssid != 'NO AP' else RED, F10, col_w)
    hud_label('ROUTE ' + route, xs[2], y+100, YELLOW, F10, col_w)
    hud_label('SSH ' + ssh_src, xs[2], y+118, DIM, F10, col_w)
    sig = DATA.get('cell_signal',0) or _net.get('cell_signal',0) or 0
    cell_ok = sig > 0
    draw_signal_bars(xs[2], y+140, sig, cell_ok)
    tech = (DATA.get('cell_tech','') or _net.get('cell_tech','--')).upper()
    operator = DATA.get('cell_operator','') or _net.get('cell_operator','--')
    hud_label(f'{tech} {sig:.0f}% {operator}', xs[2]+62, y+140, GREEN if cell_ok else RED, F10, col_w-70)
    hud_label('CELL ' + cell_ip, xs[2], y+160, WHITE if cell_ip != '--' else RED, F10, col_w)
    hud_label('TAIL ' + ts_ip, xs[2], y+180, WHITE if ts_ip != '--' else DIM, F10, col_w)
    vstat = DATA.get('voice_status', 'VC02 --') or 'VC02 --'
    vcol = GREEN if str(vstat).startswith('VC02_OK') or str(vstat).startswith('VC02_EVENT') else YELLOW
    hud_label('VOICE ' + str(vstat)[:24], xs[2], y+200, vcol, F10, col_w)
    hud_label('SYSTEM / GPS', xs[3], y+10, YELLOW, F15, col_w)
    cpu = psutil.cpu_percent(); ram = psutil.virtual_memory()
    hud_label(f'CPU {cpu:.0f}% {cpu_temp()}', xs[3], y+38, WHITE, F13, col_w)
    draw_bar(xs[3], y+62, col_w, 8, cpu, GREEN if cpu < 70 else YELLOW)
    hud_label(f'RAM {ram.percent:.0f}%', xs[3], y+78, WHITE, F13, col_w)
    hud_label(f"GPS {int(DATA.get('gps_sats',0) or 0)} SAT", xs[3], y+102, ACCENT, F13, col_w)

def hardware_health_statuses():
    thermal = DATA.get('thermal_json', {}) or {}
    thermal_ok = isinstance(thermal, dict) and bool(thermal.get('ok')) and fresh('thermal_json', 5.0)
    gps_live = fresh('gps_sats', 12.0)
    gps_sats = int(DATA.get('gps_sats', 0) or 0)
    cell_live = fresh('cell_signal', 20.0)
    return [
        ('CAMERA', 'ok' if fresh('camera_frame_ok', 4.0) else 'fail',
         'LIVE' if fresh('camera_frame_ok', 4.0) else 'CHECK CSI'),
        ('MOTOR/ENC', 'ok' if fresh('enc_m1', 4.0) else 'fail',
         'LIVE' if fresh('enc_m1', 4.0) else 'CHECK USB'),
        ('REMOTE', 'ok' if fresh('joy', 8.0) else 'warn',
         'INPUT' if fresh('joy', 8.0) else 'WAKE/PRESS'),
        ('IMU', 'ok' if fresh('heading', 4.0) else 'fail',
         'LIVE' if fresh('heading', 4.0) else 'CHECK I2C'),
        ('LIDAR', 'ok' if fresh('scan_pts', 4.0) else 'fail',
         'SCAN' if fresh('scan_pts', 4.0) else 'CHECK USB'),
        ('RADAR', 'ok' if fresh('radar', 3.0) else 'fail',
         'UART' if fresh('radar', 3.0) else 'CHECK TX/RX'),
        ('ULTRASONIC', 'ok' if fresh('us_front', 4.0) else 'fail',
         'LIVE' if fresh('us_front', 4.0) else 'CHECK ARDUINO'),
        ('INSIDE IR', 'ok' if thermal_ok else 'fail',
         '8x8 LIVE' if thermal_ok else 'CHECK 0x68/69'),
        ('OUTSIDE', 'ok' if fresh('outside_temperature', 9.0) else 'fail',
         'LIVE' if fresh('outside_temperature', 9.0) else 'CHECK 0x4B'),
        ('DALY BMS', 'ok' if fresh('bms_status', 20.0) else 'fail',
         'LIVE' if fresh('bms_status', 20.0) else 'CHECK BT'),
        ('5G', 'ok' if cell_live else 'fail',
         f'{DATA.get("cell_signal", 0) or 0:.0f}%' if cell_live else 'CHECK MODEM'),
        ('GNSS', 'ok' if gps_live and gps_sats > 0 else ('warn' if gps_live else 'fail'),
         f'{gps_sats} SAT' if gps_sats > 0 else ('SEARCHING' if gps_live else 'NO DATA')),
        ('ROS', 'ok' if fresh('ros_hb', 3.0) else 'fail',
         'READY' if fresh('ros_hb', 3.0) else 'OFFLINE'),
    ]

def draw_hardware_health_strip(x, y, w, h):
    items = hardware_health_statuses()
    failed = sum(1 for _, state, _ in items if state == 'fail')
    warned = sum(1 for _, state, _ in items if state == 'warn')
    summary_color = RED if failed else (YELLOW if warned else GREEN)
    pygame.draw.rect(screen, (5, 13, 22), (x, y, w, h))
    pygame.draw.rect(screen, summary_color, (x, y, w, h), 1)
    hud_label('HARDWARE HEALTH', x+10, y+8, summary_color, F15, 170)
    hud_label(f'{failed} FAULT  {warned} WARN', x+10, y+34, WHITE, F13, 170)
    start_x = x + 184
    columns = 7
    gap = 5
    cell_w = (w - 184 - gap*(columns-1)) // columns
    cell_h = (h - 9) // 2
    for index, (name, state, detail) in enumerate(items):
        column = index % columns
        row_index = index // columns
        bx = start_x + column*(cell_w+gap)
        by = y + 4 + row_index*cell_h
        color = GREEN if state == 'ok' else (YELLOW if state == 'warn' else RED)
        pygame.draw.rect(screen, (8, 20, 31), (bx, by, cell_w, cell_h-3))
        pygame.draw.rect(screen, color, (bx, by, 4, cell_h-3))
        pygame.draw.rect(screen, BORDER, (bx, by, cell_w, cell_h-3), 1)
        hud_label(name, bx+9, by+3, WHITE, F10, cell_w-14)
        hud_label(detail, bx+9, by+17, color, F10, cell_w-14)

def draw_hud_10inch():
    global _ip_ts, _net
    if time.monotonic() - _ip_ts > 10:
        _net = net_status()
        _ip_ts = time.monotonic()
    m, g = 14, 12
    screen.fill(BG)
    health_h = 72
    draw_hardware_health_strip(m, m, W - 2*m, health_h)
    top_y = m + health_h + g
    top_h = 400
    cam_w = 800
    draw_camera_block(m, top_y, cam_w, top_h)
    draw_hud_power(m + cam_w + g, top_y, W - (m + cam_w + g) - m, top_h)
    sy = top_y + top_h + g
    sh = 280
    draw_hud_sensor_strip(m, sy, W - 2*m, sh)
    by = sy + sh + g
    draw_hud_bottom(m, by, W - 2*m, H - by - m)

# -- 11-inch capacitive touch HMI -----------------------------------------
TOUCH_AREAS = {}
TOUCH_DOWN = None
TOUCH_DOWN_AT = 0.0
TOUCH_LAST_ACTION = 0.0
ACTIVE_TAB = 'OVERVIEW'
DETAIL_SENSOR = None
TOAST = ('Touch controls ready', 0.0, GREEN)
F30 = pygame.font.SysFont('sans', int(30 * _font_scale), bold=True)
F24 = pygame.font.SysFont('sans', int(24 * _font_scale), bold=True)
F17 = pygame.font.SysFont('sans', int(17 * _font_scale), bold=True)
F14 = pygame.font.SysFont('sans', int(14 * _font_scale))

def touch_card(rect, title, accent=ACCENT):
    pygame.draw.rect(screen, PANEL, rect, border_radius=10)
    pygame.draw.rect(screen, BORDER, rect, 1, border_radius=10)
    pygame.draw.rect(screen, accent, (rect.x, rect.y, 5, rect.h), border_radius=4)
    screen.blit(F17.render(title, True, WHITE), (rect.x+18, rect.y+12))
    pygame.draw.line(screen, (32, 54, 72), (rect.x+15, rect.y+44),
                     (rect.right-15, rect.y+44), 1)

def touch_button(key, rect, label, color=ACCENT, long_press=False,
                 subtitle=None, selected=False):
    fill = (13, 38, 54) if selected else (15, 28, 42)
    if key == TOUCH_DOWN:
        fill = (22, 66, 84)
    pygame.draw.rect(screen, fill, rect, border_radius=9)
    pygame.draw.rect(screen, color, rect, 2 if selected else 1, border_radius=9)
    text = F17.render(label, True, color if selected else WHITE)
    screen.blit(text, text.get_rect(center=(rect.centerx, rect.centery-7 if subtitle else rect.centery)))
    if subtitle:
        sub = F10.render(subtitle, True, DIM)
        screen.blit(sub, sub.get_rect(center=(rect.centerx, rect.centery+17)))
    if long_press:
        pygame.draw.rect(screen, color, (rect.x+8, rect.bottom-6, rect.w-16, 2), border_radius=1)
    TOUCH_AREAS[key] = (rect, long_press)

def touch_value(label, value, x, y, color=WHITE, width=180):
    screen.blit(F10.render(label, True, DIM), (x, y))
    surface = F17.render(str(value), True, color)
    screen.blit(surface, (x, y+17))

def recovery_systems():
    state = DATA.get('recovery_state', {}) or {}
    systems = state.get('systems', {}) if isinstance(state, dict) else {}
    return state, systems

def recovery_color(state):
    return {
        'HEALTHY': GREEN, 'NO_FIX': YELLOW, 'STALE': YELLOW,
        'SERVICE_DOWN': RED, 'FAULT': RED,
    }.get(str(state).upper(), DIM)

def set_toast(text, color=ACCENT):
    global TOAST
    TOAST = (text, time.monotonic(), color)

def safe_estop():
    zero = Twist()
    _dash_node.touch_preempt_pub.publish(Empty())
    _dash_node.touch_stop_mission_pub.publish(Empty())
    for _ in range(8):
        _dash_node.touch_stop_pub.publish(zero)
        time.sleep(0.04)

def do_touch_action(key):
    global ACTIVE_TAB, DETAIL_SENSOR, AI_ACTIVE
    if key.startswith('tab:'):
        ACTIVE_TAB = key.split(':', 1)[1]
        DETAIL_SENSOR = None
        set_toast(ACTIVE_TAB.title() + ' page')
        return
    if key.startswith('sensor:'):
        ACTIVE_TAB = 'DIAGNOSTICS'
        DETAIL_SENSOR = key.split(':', 1)[1]
        set_toast(DETAIL_SENSOR.title() + ' details')
        return
    if key == 'estop':
        threading.Thread(target=safe_estop, daemon=True).start()
        set_toast('E-STOP sent: all motion requested to stop', RED)
    elif key == 'ai':
        AI_ACTIVE = not bool(DATA.get('ai_enabled', AI_ACTIVE))
        _dash_node.touch_ai_pub.publish(Bool(data=AI_ACTIVE))
        set_toast('AI object detection ' + ('enabled' if AI_ACTIVE else 'disabled'), GREEN if AI_ACTIVE else YELLOW)
    elif key == 'face':
        enabled = not bool(DATA.get('face_tracking_enabled', True))
        _dash_node.touch_face_pub.publish(Bool(data=enabled))
        DATA.set(face_tracking_enabled=enabled)
        set_toast('Face tracking ' + ('enabled' if enabled else 'disabled'), GREEN if enabled else YELLOW)
    elif key == 'pan_left':
        target = max(700, int(DATA.get('camera_pan_us', 1300) or 1300) - 160)
        _dash_node.touch_pan_pub.publish(Int32(data=target)); DATA.set(camera_pan_us=target)
        set_toast(f'Camera pan {target} us')
    elif key == 'pan_right':
        target = min(2300, int(DATA.get('camera_pan_us', 1300) or 1300) + 160)
        _dash_node.touch_pan_pub.publish(Int32(data=target)); DATA.set(camera_pan_us=target)
        set_toast(f'Camera pan {target} us')
    elif key == 'tilt_up':
        target = min(2500, int(DATA.get('camera_tilt_us', 2100) or 2100) + 160)
        _dash_node.touch_tilt_pub.publish(Int32(data=target)); DATA.set(camera_tilt_us=target)
        set_toast(f'Camera tilt {target} us')
    elif key == 'tilt_down':
        target = max(500, int(DATA.get('camera_tilt_us', 2100) or 2100) - 160)
        _dash_node.touch_tilt_pub.publish(Int32(data=target)); DATA.set(camera_tilt_us=target)
        set_toast(f'Camera tilt {target} us')
    elif key == 'set_home':
        _dash_node.touch_home_pub.publish(Empty())
        set_toast('Current pose requested as HOME', GREEN)
    elif key == 'start_mapping':
        _dash_node.touch_start_pub.publish(Empty())
        set_toast('Autonomous mapping requested', YELLOW)
    elif key == 'return_home':
        _dash_node.touch_return_pub.publish(Empty())
        set_toast('Return-home requested', YELLOW)
    elif key == 'stop_mapping':
        _dash_node.touch_stop_mission_pub.publish(Empty())
        set_toast('Autonomy stopped and map-save requested', RED)
    elif key == 'manual':
        set_toast('Manual mode selected; use physical remote or web control', ACCENT)
    elif key == 'auto':
        set_toast('Hold START MAPPING to authorize autonomous motion', YELLOW)

def draw_touch_header():
    pygame.draw.rect(screen, (3, 9, 15), (0, 0, W, 66))
    pygame.draw.line(screen, (22, 65, 82), (0, 65), (W, 65), 1)
    screen.blit(F30.render('ATLAS CONTROL', True, WHITE), (22, 14))
    state, systems = recovery_systems()
    overall = state.get('overall', 'STARTING') if isinstance(state, dict) else 'STARTING'
    color = recovery_color('HEALTHY' if overall == 'HEALTHY' else ('FAULT' if overall == 'FAULT' else 'NO_FIX'))
    badge = pygame.Rect(350, 13, 195, 40)
    pygame.draw.rect(screen, (9, 38, 28) if color == GREEN else (48, 36, 12), badge, border_radius=8)
    pygame.draw.rect(screen, color, badge, 1, border_radius=8)
    screen.blit(F14.render('SYSTEM ' + overall, True, color), (badge.x+14, badge.y+11))
    now = time.strftime('%H:%M')
    screen.blit(F17.render(now, True, WHITE), (565, 22))
    wifi = _net.get('wifi_ip', '--'); tail = _net.get('ts_ip', '--')
    gps = systems.get('gps', {}).get('state', 'WAIT')
    status = f'Wi-Fi {wifi}    Tailscale {tail}    5G {DATA.get("cell_reg", "--")}    GPS {gps}'
    screen.blit(F14.render(status, True, DIM), (650, 23))
    touch_button('ai', pygame.Rect(W-500, 11, 145, 44),
                 'AI ' + ('ON' if DATA.get('ai_enabled', AI_ACTIVE) else 'OFF'),
                 GREEN if DATA.get('ai_enabled', AI_ACTIVE) else YELLOW)
    face_on = bool(DATA.get('face_tracking_enabled', True))
    touch_button('face', pygame.Rect(W-345, 11, 150, 44),
                 'FACE ' + ('ON' if face_on else 'OFF'), GREEN if face_on else YELLOW)
    touch_button('estop', pygame.Rect(W-180, 8, 164, 50), 'E-STOP', RED)

def draw_touch_camera(rect):
    global _detect_frame
    touch_card(rect, 'LIVE CAMERA', GREEN if fresh('camera_frame_ok',4) else RED)
    feed=pygame.Rect(rect.x+2,rect.y+47,rect.w-4,rect.h-126)
    cam_frame=None
    with _dash_node._cam_lock:
        if _dash_node._cam_frame is not None: cam_frame=_dash_node._cam_frame.copy()
    if cam_frame is not None:
        frame=cv2.resize(cam_frame,(feed.w,feed.h))
        screen.blit(pygame.surfarray.make_surface(np.rot90(frame)),feed.topleft)
        if ENABLE_YOLO and AI_ACTIVE:
            with _detect_frame_lk: _detect_frame=cam_frame.copy()
            with _detect_lock:
                detections=list(_detect_results); sw,sh=_detect_result_size
            for x1,y1,x2,y2,label,confidence in detections:
                box=pygame.Rect(feed.x+int(x1*feed.w/max(1,sw)),feed.y+int(y1*feed.h/max(1,sh)),
                                max(1,int((x2-x1)*feed.w/max(1,sw))),max(1,int((y2-y1)*feed.h/max(1,sh))))
                pygame.draw.rect(screen,ACCENT,box,2)
                tag=F10.render(f'{label} {confidence*100:.0f}%',True,WHITE)
                tagbox=pygame.Rect(box.x,max(feed.y,box.y-22),tag.get_width()+12,22)
                pygame.draw.rect(screen,(4,45,58),tagbox,border_radius=3); screen.blit(tag,(tagbox.x+6,tagbox.y+4))
        live=F10.render('● LIVE',True,GREEN); pygame.draw.rect(screen,(2,18,20),(feed.x+10,feed.y+8,68,24),border_radius=5); screen.blit(live,(feed.x+18,feed.y+14))
    else:
        pygame.draw.rect(screen,(7,15,24),feed)
        msg=F24.render('NO CAMERA SIGNAL',True,RED); screen.blit(msg,msg.get_rect(center=feed.center))
    bh = 66; gap = 8; margin = 10
    bw = (rect.w - margin*2 - gap*3)//4
    y = rect.bottom - bh - 9
    buttons = [('pan_left','PAN LEFT'), ('tilt_up','TILT UP'),
               ('tilt_down','TILT DOWN'), ('pan_right','PAN RIGHT')]
    for index, (key, label) in enumerate(buttons):
        touch_button(key, pygame.Rect(rect.x+margin+index*(bw+gap), y, bw, bh), label, ACCENT)

def draw_touch_awareness(rect):
    touch_card(rect,'LiDAR + RADAR AWARENESS',ACCENT)
    cx=rect.centerx; cy=rect.bottom-105; max_r=min(180,rect.w//2-32)
    # Semicircular automotive-style range plot.
    for factor,label in ((1.0,'4 m'),(.75,'3 m'),(.5,'2 m'),(.25,'1 m')):
        rr=int(max_r*factor)
        pygame.draw.arc(screen,(34,64,78),(cx-rr,cy-rr,rr*2,rr*2),0,math.pi,1)
        hud_label(label,cx+rr-30,cy-18,DIM,F10,28)
    for deg in range(0,181,30):
        rad=math.radians(deg); hud_line(cx,cy,cx+max_r*math.cos(rad),cy-max_r*math.sin(rad),(25,52,66),1)
    # Sector distance markers from the real LiDAR summary.
    sectors=[('LEFT',DATA.get('lidar_left',-1),150),('FRONT',DATA.get('lidar_front',-1),90),('RIGHT',DATA.get('lidar_right',-1),30)]
    for label,mm,deg in sectors:
        live=fresh('scan_pts',3) and mm is not None and mm>=0
        rr=min(max_r,max(18,int((mm if live else 4000)/4000*max_r)))
        rad=math.radians(deg); px=cx+int(rr*math.cos(rad)); py=cy-int(rr*math.sin(rad))
        _,color=sensor_word(mm,live); pygame.draw.circle(screen,color,(px,py),8)
        hud_label(label,px-28,py-25,color,F10,56)
    # Real radar targets share the same plot.
    targets=parse_radar_targets(DATA.get('radar',''))
    for target in targets[:4]:
        x_m=target['x']/1000.0; y_m=target['y']/1000.0
        px=cx+int(max(-1,min(1,x_m/4))*max_r); py=cy-int(max(0,min(1,y_m/4))*max_r)
        pygame.draw.circle(screen,RED,(px,py),7); pygame.draw.circle(screen,(255,180,80),(px,py),12,1)
    # Rover footprint at plot origin.
    rover=pygame.Rect(cx-18,cy-32,36,54); pygame.draw.rect(screen,(30,54,67),rover,border_radius=8); pygame.draw.rect(screen,ACCENT,rover,2,border_radius=8)
    hud_label(f'RADAR {len(targets)} TARGET' + ('S' if len(targets)!=1 else ''),rect.x+18,rect.y+55,ORANGE,F13,180)
    draw_touch_range_overlay(rect)

def draw_touch_power(rect):
    touch_card(rect,'POWER',ACCENT)
    ok=fresh('bms_status',20); pct=float(DATA.get('bms_pct',0) or 0); voltage=float(DATA.get('bms_voltage',0) or 0); current=float(DATA.get('bms_current',0) or 0); watts=float(DATA.get('bms_power',voltage*current) or 0)
    color=GREEN if ok and pct>30 else (YELLOW if ok and pct>10 else RED)
    screen.blit(F30.render(f'{pct:.0f}%',True,WHITE if ok else RED),(rect.x+22,rect.y+66))
    touch_value('VOLTAGE',f'{voltage:.2f} V',rect.x+22,rect.y+127,ACCENT)
    touch_value('CURRENT',f'{current:+.2f} A',rect.x+190,rect.y+127,ACCENT)
    touch_value('LIVE POWER',f'{watts:.1f} W',rect.x+360,rect.y+127,GREEN if ok else RED)
    # Large battery pictogram.
    bx=rect.right-92; by=rect.y+58; battery=pygame.Rect(bx,by,55,112)
    pygame.draw.rect(screen,DIM,battery,3,border_radius=7); pygame.draw.rect(screen,DIM,(bx+17,by-8,22,9),border_radius=2)
    fill_h=int(max(0,min(100,pct))/100*(battery.h-10)); pygame.draw.rect(screen,color,(bx+6,battery.bottom-5-fill_h,battery.w-12,fill_h),border_radius=3)
    cells=[DATA.get(f'bms_cell{i}',0) or 0 for i in range(1,5)]
    cell_gap=10; cell_w=(rect.w-44-cell_gap*3)//4
    for i,value in enumerate(cells):
        cr=pygame.Rect(rect.x+18+i*(cell_w+cell_gap),rect.y+205,cell_w,84)
        pygame.draw.rect(screen,(10,25,35),cr,border_radius=7); pygame.draw.rect(screen,BORDER,cr,1,border_radius=7)
        level=max(0,min(1,(float(value)-3.0)/.6)); pygame.draw.rect(screen,GREEN,(cr.x+10,cr.bottom-12-int(level*48),cr.w-20,int(level*48)),border_radius=3)
        hud_label(f'C{i+1} {float(value):.3f}V',cr.x+10,cr.bottom-22,DIM,F10,cr.w-20)
    jv,ji,jw=jetson_input_power(); motor_v=float(DATA.get('voltage',0) or 0)
    pygame.draw.rect(screen,(9,25,34),(rect.x+18,rect.y+310,rect.w-36,50),border_radius=7)
    hud_label(f'JETSON INPUT  {jv:.1f}V  {ji:.2f}A  {jw:.1f}W',rect.x+32,rect.y+326,GREEN if jv>1 else YELLOW,F13,rect.w-64)
    pygame.draw.rect(screen,(9,25,34),(rect.x+18,rect.y+370,rect.w-36,44),border_radius=7)
    hud_label(f'MOTOR BOARD  {motor_v:.2f}V  current shunt unavailable',rect.x+32,rect.y+383,YELLOW,F13,rect.w-64)

def draw_touch_range_overlay(rect):
    """Live LiDAR and ultrasonic distances over the combined awareness card."""
    band = pygame.Rect(rect.x+8, rect.bottom-94, rect.w-16, 86)
    pygame.draw.rect(screen, (4, 14, 23), band, border_radius=7)
    pygame.draw.rect(screen, BORDER, band, 1, border_radius=7)
    lidar_live = fresh('scan_pts', 3.0)
    ultra_live = fresh('us_front', 4.0)
    lidar = [
        ('NEAR', DATA.get('lidar_min', -1)), ('FRONT', DATA.get('lidar_front', -1)),
        ('LEFT', DATA.get('lidar_left', -1)), ('RIGHT', DATA.get('lidar_right', -1)),
    ]
    ultra = [
        ('FRONT', DATA.get('us_front', -1)), ('LEFT', DATA.get('us_left', -1)),
        ('RIGHT', DATA.get('us_right', -1)),
    ]
    hud_label('LiDAR', band.x+10, band.y+8, ACCENT, F13, 60)
    cell = (band.w-76)//4
    for i,(label,value) in enumerate(lidar):
        live = lidar_live and value is not None and value >= 0
        _, color = sensor_word(value, live)
        x=band.x+72+i*cell
        hud_label(label, x, band.y+7, DIM, F10, cell-4)
        hud_label(f'{int(value)} mm' if live else '--', x, band.y+25, color, F13, cell-4)
    pygame.draw.line(screen,(32,54,72),(band.x+8,band.y+45),(band.right-8,band.y+45),1)
    hud_label('ULTRA', band.x+10, band.y+54, GREEN, F13, 60)
    cell=(band.w-76)//3
    for i,(label,value) in enumerate(ultra):
        live=ultra_live and value is not None and value >= 0
        _,color=sensor_word(value,live)
        x=band.x+72+i*cell
        hud_label(label, x, band.y+51, DIM, F10, cell-4)
        hud_label(f'{int(value)} mm' if live else '--', x+62, band.y+51, color, F13, cell-68)

def draw_touch_middle(y, h):
    gap = 10; margin = 12
    widths = [330, 430, 500, W-2*margin-3*gap-1260]
    x = margin
    # Drive
    r = pygame.Rect(x, y, widths[0], h); touch_card(r, 'DRIVE', ACCENT)
    motion = DATA.get('safety_status', 'STOPPED') or 'STOPPED'
    stopped = abs(DATA.get('cmd_vx', 0) or 0) < .01 and abs(DATA.get('cmd_wz', 0) or 0) < .01
    screen.blit(F24.render('STOPPED' if stopped else 'MOVING', True, GREEN if stopped else YELLOW), (x+20, y+60))
    touch_button('manual', pygame.Rect(x+18, y+110, 140, 58), 'MANUAL', ACCENT, selected=True)
    touch_button('auto', pygame.Rect(x+170, y+110, 140, 58), 'AUTO', YELLOW)
    hud_label(str(motion)[:42], x+18, y+184, DIM, F10, r.w-36)
    x += widths[0]+gap
    # Navigation
    r = pygame.Rect(x, y, widths[1], h); touch_card(r, 'NAVIGATION', ACCENT)
    touch_button('tab:MAP', pygame.Rect(x+18, y+58, 190, 60), 'MAP', ACCENT)
    touch_button('set_home', pygame.Rect(x+220, y+58, 190, 60), 'SET HOME', GREEN)
    touch_button('start_mapping', pygame.Rect(x+18, y+132, 190, 68), 'START MAP', YELLOW, True, 'HOLD 1.2 SEC')
    touch_button('return_home', pygame.Rect(x+220, y+132, 190, 68), 'RETURN HOME', YELLOW, True, 'HOLD 1.2 SEC')
    x += widths[1]+gap
    # Environment
    r = pygame.Rect(x, y, widths[2], h); touch_card(r, 'ENVIRONMENT', GREEN)
    thermal = DATA.get('thermal_json', {}) or {}
    pixels = thermal.get('pixels', []) if isinstance(thermal, dict) else []
    thermal_live = fresh('thermal_json', 8.0) and len(pixels) == 64 and bool(thermal.get('ok'))
    inside = float(thermal.get('avg_c', 0.0) or 0.0) if thermal_live else None
    outside = DATA.get('outside_temperature', None)
    # Left: inside AMG8833 heatmap. Right: outside BME680 measurements.
    # The compact overview intentionally keeps each value on its own line;
    # tapping either side opens the full two-graph environment page.
    grid_x, grid_y, cell = x+18, y+54, 12
    thermal_rect = pygame.Rect(grid_x, grid_y, cell*8, cell*8)
    if thermal_live:
        mn = float(thermal.get('min_c', min(pixels)) or 0.0)
        mx = float(thermal.get('max_c', max(pixels)) or 0.0)
        hot_i = max(range(64), key=lambda i: pixels[i])
        for rr in range(8):
            for cc in range(8):
                idx = rr*8+cc
                box = pygame.Rect(grid_x+cc*cell, grid_y+rr*cell, cell-1, cell-1)
                pygame.draw.rect(screen, thermal_color(pixels[idx], mn, mx), box)
                if idx == hot_i:
                    pygame.draw.rect(screen, WHITE, box, 2)
        pygame.draw.rect(screen, GREEN, thermal_rect, 2)
        hud_label(f'AVG {inside:.1f} C', x+18, y+158, WHITE, F13, 112)
        hud_label(f'{mn:.1f} - {mx:.1f} C', x+18, y+179, DIM, F10, 112)
    else:
        pygame.draw.rect(screen, (18,24,34), thermal_rect)
        pygame.draw.rect(screen, RED, thermal_rect, 2)
        hud_label('8x8 OFFLINE', x+18, y+158, RED, F13, 112)
    hud_label('AMG8833 INSIDE', x+18, y+37, GREEN if thermal_live else RED, F10, 112)
    TOUCH_AREAS['sensor:thermal']=(thermal_rect,False)
    outside_live = outside is not None and fresh('outside_temperature',9)
    iaq = DATA.get('outside_iaq', None)
    quality = str(DATA.get('outside_air_quality', 'WARMING'))
    qcolor = GREEN if quality in ('EXCELLENT','GOOD') else (YELLOW if quality == 'MODERATE' else ORANGE)
    bx = x + 136
    hud_label('BME680 OUTSIDE', bx, y+37, GREEN if outside_live else RED, F10, 340)
    touch_value('TEMPERATURE', f'{outside:.1f} C' if outside_live else 'FAULT', bx, y+53, GREEN if outside_live else RED, 155)
    touch_value('HUMIDITY', f'{DATA.get("outside_humidity",0):.0f} %' if fresh('outside_humidity',9) else '--', bx+165, y+53, WHITE if fresh('outside_humidity',9) else RED, 150)
    touch_value('PRESSURE', f'{DATA.get("outside_pressure",0):.0f} hPa' if fresh('outside_pressure',9) else '--', bx, y+105, WHITE, 155)
    touch_value('IAQ ESTIMATE', f'{iaq:.0f} {quality}' if iaq is not None and fresh('outside_iaq',9) else 'WARMING', bx+165, y+105, qcolor, 150)
    eco2 = DATA.get('outside_eco2', None)
    hud_label('eCO2 EST. --' if eco2 is None else f'eCO2 EST. {eco2:.0f} ppm', bx, y+159, DIM, F10, 155)
    hud_label(f'VOC {DATA.get("outside_gas",0)/1000:.1f} kohm', bx+165, y+159, DIM, F10, 150)

    # A small dual trend: orange is inside AMG8833 average, cyan is outside
    # BME680 ambient temperature. Full labelled graphs open when tapped.
    chart = pygame.Rect(x+136, y+188, 340, 39)
    pygame.draw.rect(screen, (5,11,19), chart)
    pygame.draw.rect(screen, BORDER, chart, 1)
    inside_hist = [row[3] for row in THERMAL_HISTORY[-60:]]
    outside_hist = [value for _, value in AMBIENT_HISTORY[-60:]]
    combined = [v for v in inside_hist + outside_hist if 5.0 <= v <= 60.0]
    if combined:
        low, high = min(combined)-0.3, max(combined)+0.3
        if high-low < 1.0: high = low+1.0
        def mini_points(values):
            return [(chart.x+4+int(i*(chart.w-8)/max(1,len(values)-1)),
                     max(chart.y+4, min(chart.bottom-4,
                         chart.bottom-4-int((v-low)*(chart.h-8)/(high-low)))))
                    for i,v in enumerate(values)]
        for values,color in ((inside_hist,ORANGE),(outside_hist,ACCENT)):
            points=mini_points(values)
            if len(points)>1: pygame.draw.lines(screen,color,False,points,2)
    hud_label('INSIDE', chart.x+5, chart.y+3, ORANGE, F10, 55)
    hud_label('OUTSIDE', chart.x+64, chart.y+3, ACCENT, F10, 65)
    TOUCH_AREAS['sensor:ambient']=(pygame.Rect(bx,y+34,340,196),False)
    x += widths[2]+gap
    # Network
    r = pygame.Rect(x, y, widths[3], h); touch_card(r, 'NETWORK + JETSON LOAD', ACCENT)
    rows = [('Wi-Fi', _net.get('wifi_ip','--')), ('Tailscale', _net.get('ts_ip','--')),
            ('5G', str(DATA.get('cell_tech','--'))), ('GPS', f'{int(DATA.get("gps_sats",0) or 0)} SAT')]
    for i,(lab,val) in enumerate(rows):
        yy=y+52+i*27; hud_label(lab, x+18, yy, DIM, F10, 90); hud_label(val, x+108, yy, WHITE if val!='--' else RED, F13, r.w-126)
    cpu = float(psutil.cpu_percent() or 0); ram = float(psutil.virtual_memory().percent or 0)
    gpu = gpu_load_percent(); loads = [('CPU',cpu),('GPU',gpu),('RAM',ram)]
    for i,(label,value) in enumerate(loads):
        yy=y+164+i*24; shown=0.0 if value is None else value
        color=GREEN if shown < 65 else (YELLOW if shown < 85 else RED)
        hud_label(label, x+18, yy, DIM, F10, 42)
        hud_label('--' if value is None else f'{shown:.0f}%', x+58, yy, color, F10, 42)
        draw_bar(x+104, yy+3, r.w-124, 9, shown, color)
    hud_label('JETSON '+cpu_temp(),x+r.w-105,y+52,DIM,F10,88)

def draw_touch_health(y, h):
    margin=12; fault_w=610; gap=10
    health=pygame.Rect(margin,y,W-2*margin-fault_w-gap,h)
    fault=pygame.Rect(health.right+gap,y,fault_w,h)
    touch_card(health, 'SYSTEM HEALTH - TAP ANY SENSOR FOR DETAILS', GREEN)
    state, systems = recovery_systems()
    order=['lidar','camera','imu','radar','ultrasonic','thermal','gps','bms','odometry','encoder_fl','ambient','cellular']
    cols=6; pad=12; cell_gap=8; cell_w=(health.w-pad*2-cell_gap*(cols-1))//cols; cell_h=82
    for index,name in enumerate(order):
        info=systems.get(name,{})
        status=info.get('state','WAIT'); color=recovery_color(status)
        row=index//cols; col=index%cols
        rect=pygame.Rect(health.x+pad+col*(cell_w+cell_gap), health.y+53+row*(cell_h+8), cell_w, cell_h)
        pygame.draw.rect(screen,(10,24,35),rect,border_radius=7); pygame.draw.rect(screen,color,rect,1,border_radius=7)
        pygame.draw.circle(screen,color,(rect.x+18,rect.y+19),8)
        hud_label(name.replace('_fl','').upper(),rect.x+34,rect.y+9,WHITE,F13,rect.w-40)
        hud_label(status,rect.x+12,rect.y+39,color,F10,rect.w-24)
        hud_label(str(info.get('detail','waiting'))[:22],rect.x+12,rect.y+58,DIM,F10,rect.w-24)
        TOUCH_AREAS['sensor:'+name]=(rect,False)
    touch_card(fault, 'FAULT DIAGNOSIS', RED)
    faults=[(name,info) for name,info in systems.items() if info.get('state')!='HEALTHY']
    if not faults:
        screen.blit(F24.render('ALL REQUIRED SYSTEMS HEALTHY',True,GREEN),(fault.x+22,fault.y+70))
    else:
        yy=fault.y+60
        for name,info in faults[:3]:
            color=recovery_color(info.get('state'))
            screen.blit(F17.render(name.upper()+'  '+str(info.get('state')),True,color),(fault.x+22,yy))
            hud_label(str(info.get('detail',''))[:68],fault.x+22,yy+27,DIM,F13,fault.w-44)
            yy+=65
    recovery=DATA.get('recovery_status',None)
    if not recovery:
        recovery='Overall '+str(state.get('overall','STARTING'))+'; tap a sensor for details'
    recovery=str(recovery)
    hud_label('LATEST: '+recovery[:72],fault.x+22,fault.bottom-36,ACCENT,F10,fault.w-44)

def draw_live_sensor_detail(rect, name, info):
    """Render a touch-friendly, continuously updating sensor detail page."""
    color = recovery_color(info.get('state'))
    live = str(info.get('state', '')).upper() == 'HEALTHY'
    hud_label('LIVE TELEMETRY', rect.x+34, rect.y+58, color, F17, 260)
    hud_label('Updates automatically from ROS 2; no refresh button required', rect.x+300, rect.y+61, DIM, F13, rect.w-350)

    if name in ('ambient', 'thermal'):
        draw_environment_panel(rect.x+34, rect.y+92, rect.w-68, rect.h-128)
    elif name == 'ultrasonic':
        labels = [('LEFT', 'us_left'), ('FRONT', 'us_front'), ('RIGHT', 'us_right')]
        gap = 18
        card_w = (rect.w - 68 - gap*2)//3
        top = rect.y + 125
        for index, (label, key) in enumerate(labels):
            value = DATA.get(key, -1)
            valid = fresh(key, 4.0) and value is not None and float(value) >= 0
            mm = float(value) if valid else -1.0
            _, sensor_color = sensor_word(mm, valid)
            tile = pygame.Rect(rect.x+34+index*(card_w+gap), top, card_w, 310)
            pygame.draw.rect(screen, (7, 21, 32), tile, border_radius=12)
            pygame.draw.rect(screen, sensor_color, tile, 2, border_radius=12)
            title = F24.render(label, True, WHITE)
            screen.blit(title, title.get_rect(center=(tile.centerx, tile.y+42)))
            value_text = 'NO ECHO' if not valid else f'{mm:.0f} mm'
            reading = F30.render(value_text, True, sensor_color)
            screen.blit(reading, reading.get_rect(center=(tile.centerx, tile.y+112)))
            zone = 'FAULT / NO DATA' if not valid else ('STOP ZONE' if mm < 250 else ('CAUTION' if mm < 500 else 'CLEAR'))
            zone_text = F17.render(zone, True, sensor_color)
            screen.blit(zone_text, zone_text.get_rect(center=(tile.centerx, tile.y+165)))
            bar = pygame.Rect(tile.x+32, tile.y+215, tile.w-64, 28)
            pygame.draw.rect(screen, (20, 39, 51), bar, border_radius=8)
            if valid:
                fill = int(max(0, min(1, mm/3000.0))*bar.w)
                pygame.draw.rect(screen, sensor_color, (bar.x, bar.y, fill, bar.h), border_radius=8)
            hud_label(f'AGE {DATA.age(key):.1f}s', tile.x+32, tile.y+268, DIM, F13, tile.w-64)
        hud_label('LiDAR is the primary navigation layer; these three sensors provide close-range backup protection.',
                  rect.x+34, rect.bottom-48, ACCENT, F14, rect.w-68)
    elif name == 'camera':
        feed = pygame.Rect(rect.x+34, rect.y+102, int(rect.w*.70), rect.h-165)
        pygame.draw.rect(screen, (0, 0, 0), feed, border_radius=10)
        cam_frame = None
        with _dash_node._cam_lock:
            if _dash_node._cam_frame is not None:
                cam_frame = _dash_node._cam_frame.copy()
        if cam_frame is not None:
            frame = cv2.resize(cam_frame, (feed.w, feed.h))
            screen.blit(pygame.surfarray.make_surface(np.rot90(frame)), feed.topleft)
            pygame.draw.rect(screen, GREEN, feed, 2, border_radius=10)
        else:
            msg = F24.render('NO CAMERA SIGNAL', True, RED)
            screen.blit(msg, msg.get_rect(center=feed.center))
            pygame.draw.rect(screen, RED, feed, 2, border_radius=10)
        side_x = feed.right + 28
        touch_value('STREAM', 'LIVE' if fresh('camera_frame_ok', 4) else 'STALE', side_x, rect.y+125,
                    GREEN if fresh('camera_frame_ok', 4) else RED, rect.right-side_x-24)
        touch_value('AI DETECTION', 'ON' if DATA.get('ai_enabled', AI_ACTIVE) else 'OFF', side_x, rect.y+220,
                    GREEN if DATA.get('ai_enabled', AI_ACTIVE) else YELLOW, rect.right-side_x-24)
        with _detect_lock:
            detection_count = len(_detect_results)
        touch_value('OBJECTS', str(detection_count), side_x, rect.y+315, ACCENT, rect.right-side_x-24)
        touch_value('FACE TRACKING', 'ON' if DATA.get('face_tracking_enabled', True) else 'OFF', side_x, rect.y+410,
                    GREEN if DATA.get('face_tracking_enabled', True) else YELLOW, rect.right-side_x-24)
        hud_label(str(DATA.get('face_tracking_status', 'waiting'))[:48], side_x, rect.y+485, DIM, F13, rect.right-side_x-24)
    elif name == 'imu':
        imu = DATA.get('imu_full', {}) or {}
        values = [
            ('ROLL', DATA.get('roll', imu.get('roll', 0)), 'deg'),
            ('PITCH', DATA.get('pitch', imu.get('pitch', 0)), 'deg'),
            ('HEADING', DATA.get('heading', imu.get('heading', 0)), 'deg'),
            ('ACCEL X', imu.get('ax', 0), 'm/s2'), ('ACCEL Y', imu.get('ay', 0), 'm/s2'),
            ('ACCEL Z', imu.get('az', 0), 'm/s2'), ('GYRO X', imu.get('gx', 0), 'rad/s'),
            ('GYRO Y', imu.get('gy', 0), 'rad/s'), ('GYRO Z', imu.get('gz', 0), 'rad/s'),
            ('MAG X', imu.get('mx', 0), 'uT'), ('MAG Y', imu.get('my', 0), 'uT'),
            ('MAG Z', imu.get('mz', 0), 'uT'),
        ]
        cols = 3; gap = 14; left = rect.x+34; top = rect.y+115
        card_w = (rect.w-68-gap*(cols-1))//cols; card_h = 105
        for index, (label, value, unit) in enumerate(values):
            row, col = divmod(index, cols)
            tile = pygame.Rect(left+col*(card_w+gap), top+row*(card_h+gap), card_w, card_h)
            pygame.draw.rect(screen, (8, 22, 34), tile, border_radius=8)
            pygame.draw.rect(screen, GREEN if fresh('imu_full', 4) else RED, tile, 1, border_radius=8)
            hud_label(label, tile.x+16, tile.y+13, DIM, F13, tile.w-32)
            hud_label(f'{float(value or 0):+.3f} {unit}', tile.x+16, tile.y+48, WHITE, F17, tile.w-32)
        hud_label(f'MOTOR-BOARD IMU COMPARISON: roll {float(DATA.get("yb_roll",0) or 0):+.1f} deg  '
                  f'pitch {float(DATA.get("yb_pitch",0) or 0):+.1f} deg  heading {float(DATA.get("yb_heading",0) or 0):.1f} deg',
                  rect.x+34, rect.bottom-45, ACCENT, F14, rect.w-68)
    elif name == 'lidar':
        plot = pygame.Rect(rect.x+34, rect.y+105, int(rect.w*.60), rect.h-180)
        pygame.draw.rect(screen, (3,14,22), plot, border_radius=10); pygame.draw.rect(screen, BORDER, plot, 1, border_radius=10)
        cx, cy = plot.centerx, plot.bottom-46; radius = min(plot.w//2-50, plot.h-80)
        for factor,label in ((1.0,'4 m'),(.75,'3 m'),(.5,'2 m'),(.25,'1 m')):
            rr=int(radius*factor); pygame.draw.arc(screen,(31,70,88),(cx-rr,cy-rr,rr*2,rr*2),0,math.pi,1)
            hud_label(label,cx+rr-32,cy-18,DIM,F10,30)
        sectors=[('LEFT',DATA.get('lidar_left',-1),150),('FRONT',DATA.get('lidar_front',-1),90),('RIGHT',DATA.get('lidar_right',-1),30)]
        for label,mm,deg in sectors:
            valid=fresh('scan_pts',3) and mm is not None and mm>=0
            rr=min(radius,max(20,int((mm if valid else 4000)/4000*radius)))
            angle=math.radians(deg); px=cx+int(rr*math.cos(angle)); py=cy-int(rr*math.sin(angle))
            _,dot=sensor_word(mm,valid); pygame.draw.circle(screen,dot,(px,py),11); hud_label(label,px-34,py-30,dot,F13,70)
        side_x=plot.right+28
        values=[('NEAREST',DATA.get('lidar_min',-1)),('FRONT',DATA.get('lidar_front',-1)),('LEFT',DATA.get('lidar_left',-1)),('RIGHT',DATA.get('lidar_right',-1))]
        for i,(label,value) in enumerate(values):
            valid=fresh('scan_pts',3) and value is not None and value>=0; _,vc=sensor_word(value,valid)
            touch_value(label,f'{int(value)} mm' if valid else 'NO DATA',side_x,rect.y+125+i*92,vc,rect.right-side_x-30)
        touch_value('VALID POINTS',str(int(DATA.get('scan_pts',0) or 0)),side_x,rect.y+505,ACCENT)
    elif name == 'radar':
        plot = pygame.Rect(rect.x+34, rect.y+105, int(rect.w*.62), rect.h-180)
        pygame.draw.rect(screen,(2,18,13),plot,border_radius=10); pygame.draw.rect(screen,(0,130,80),plot,1,border_radius=10)
        targets=parse_radar_targets(DATA.get('radar',''))
        draw_radar_ppi(plot.centerx, plot.centery, min(plot.w,plot.h)//2-38, targets, time.time())
        side_x=plot.right+28
        touch_value('TARGETS',str(len(targets)),side_x,rect.y+125,GREEN if fresh('radar',3) else RED)
        if targets:
            nearest=min(targets,key=lambda target: target['dist'])
            touch_value('NEAREST',f"{nearest['dist']:.0f} mm",side_x,rect.y+220,ORANGE)
            touch_value('POSITION',f"X {nearest['x']}  Y {nearest['y']} mm",side_x,rect.y+315,WHITE,rect.right-side_x-25)
            touch_value('SPEED',f"{nearest['speed']:+d} cm/s",side_x,rect.y+410,ACCENT)
        else:
            touch_value('DETECTION','NO MOVING TARGET',side_x,rect.y+220,YELLOW,rect.right-side_x-25)
        hud_label(str(DATA.get('radar','waiting for UART frames'))[:80],side_x,rect.y+515,DIM,F10,rect.right-side_x-25)
    elif name == 'encoder_fl':
        # The motor controller exposes four independent channels.  Show all
        # four together instead of sending this sensor through the generic
        # one-value detail template.
        motors=[('FRONT RIGHT','M1','fr',DATA.get('enc_m1','--'),'enc_m1'),
                ('FRONT LEFT','M2','fl',DATA.get('enc_m2','--'),'enc_m2'),
                ('BACK RIGHT','M3','br',DATA.get('enc_m3','--'),'enc_m3'),
                ('BACK LEFT','M4','bl',DATA.get('enc_m4','--'),'enc_m4')]
        gap=12; left=rect.x+34; top=rect.y+105
        card_w=(rect.w-68-gap)//2; card_h=max(105,(rect.h-145-gap)//2)
        for index,(position,channel,wheel_key,count,key) in enumerate(motors):
            col=index%2; row=index//2
            tile=pygame.Rect(left+col*(card_w+gap),top+row*(card_h+gap),card_w,card_h)
            is_live=fresh(key,4.0); tile_color=GREEN if is_live else RED
            pygame.draw.rect(screen,(9,23,34),tile,border_radius=9)
            pygame.draw.rect(screen,tile_color,tile,2,border_radius=9)
            hud_label(f'{position} / {channel}',tile.x+16,tile.y+13,ACCENT,F17,tile.w-32)
            rpm=float(DATA.get(f'{wheel_key}_rpm',0) or 0)
            mps=float(DATA.get(f'{wheel_key}_mps',0) or 0)
            distance=float(DATA.get(f'{wheel_key}_distance',0) or 0)
            moving=abs(rpm)>=0.5
            touch_value('STATE','MOVING' if moving else 'STOPPED',tile.x+16,tile.y+42,GREEN if moving else DIM,tile.w//2-20)
            touch_value('SPEED',f'{abs(rpm):.1f} RPM',tile.x+tile.w//2,tile.y+42,tile_color,tile.w//2-16)
            hud_label(f'{abs(mps):.3f} m/s   distance {distance:+.3f} m   raw {count}',tile.x+16,tile.bottom-24,DIM,F10,tile.w-32)
        hud_label('Physical map: M1 front-right | M2 front-left | M3 back-right | M4 back-left',
                  rect.x+34,rect.bottom-30,DIM,F13,rect.w-68)
    else:
        # All other sensors still receive a useful live status view.
        card=pygame.Rect(rect.x+34,rect.y+110,rect.w-68,270)
        pygame.draw.rect(screen,(9,23,34),card,border_radius=10); pygame.draw.rect(screen,color,card,1,border_radius=10)
        touch_value('STATE',str(info.get('state','WAIT')),card.x+28,card.y+30,color)
        touch_value('DATA AGE',f"{info.get('age_s','--')} s",card.x+320,card.y+30,WHITE)
        hud_label('DETAIL',card.x+28,card.y+125,DIM,F13,100)
        hud_label(str(info.get('detail','waiting for sensor data')),card.x+28,card.y+158,WHITE,F17,card.w-56)
        hud_label('Automatic recovery: '+('ENABLED' if info.get('auto_recovery') else 'MONITOR ONLY'),card.x+28,card.y+215,ACCENT,F13,card.w-56)

def draw_touch_tab_page():
    margin=16; rect=pygame.Rect(margin,82,W-2*margin,H-190)
    touch_card(rect, ACTIVE_TAB + (' / '+DETAIL_SENSOR.upper() if DETAIL_SENSOR else ''), ACCENT)
    state, systems=recovery_systems()
    if ACTIVE_TAB=='DIAGNOSTICS':
        if DETAIL_SENSOR:
            draw_live_sensor_detail(rect, DETAIL_SENSOR, systems.get(DETAIL_SENSOR,{}))
        else:
            names=list(systems); yy=rect.y+62
            for name in names:
                info=systems.get(name,{})
                color=recovery_color(info.get('state'))
                pygame.draw.rect(screen,(10,24,35),(rect.x+20,yy,rect.w-40,82),border_radius=8)
                screen.blit(F17.render(name.upper(),True,WHITE),(rect.x+38,yy+13))
                screen.blit(F17.render(str(info.get('state','WAIT')),True,color),(rect.x+280,yy+13))
                hud_label('DETAIL: '+str(info.get('detail','waiting')),rect.x+38,yy+43,DIM,F13,rect.w-76)
                yy+=94
                if yy>rect.bottom-95: break
    elif ACTIVE_TAB=='SENSORS':
        order=list(systems)
        cols=4; gap=12; pad=22; cw=(rect.w-pad*2-gap*(cols-1))//cols; ch=128
        for index,name in enumerate(order):
            info=systems.get(name,{})
            row=index//cols; col=index%cols
            bx=rect.x+pad+col*(cw+gap); by=rect.y+58+row*(ch+gap)
            if by+ch>rect.bottom-15: break
            tile=pygame.Rect(bx,by,cw,ch); color=recovery_color(info.get('state'))
            pygame.draw.rect(screen,(9,23,34),tile,border_radius=9)
            pygame.draw.rect(screen,color,tile,1,border_radius=9)
            screen.blit(F17.render(name.upper(),True,WHITE),(bx+16,by+13))
            screen.blit(F14.render(str(info.get('state','WAIT')),True,color),(bx+16,by+43))
            hud_label(str(info.get('detail','waiting'))[:48],bx+16,by+70,DIM,F13,cw-32)
            hud_label(f"AGE {info.get('age_s','--')}s   AUTO {'YES' if info.get('auto_recovery') else 'NO'}",bx+16,by+98,ACCENT,F10,cw-32)
            TOUCH_AREAS['sensor:'+name]=(tile,False)
    elif ACTIVE_TAB=='DRIVE':
        screen.blit(F30.render('DRIVE TELEMETRY',True,WHITE),(rect.x+34,rect.y+65))
        values=[('FRONT RIGHT / M1',DATA.get('fr',0),DATA.get('enc_m1','--')),
                ('FRONT LEFT / M2',DATA.get('fl',0),DATA.get('enc_m2','--')),
                ('BACK RIGHT / M3',DATA.get('rr',0),DATA.get('enc_m3','--')),
                ('BACK LEFT / M4',DATA.get('rl',0),DATA.get('enc_m4','--'))]
        gap=12; left=rect.x+34; top=rect.y+105
        side_w=440 if rect.w>=1400 else 0
        grid_w=rect.w-68-side_w-(gap if side_w else 0)
        card_w=(grid_w-gap)//2; card_h=max(105,(rect.h-125-gap)//2)
        for i,(name,power,encoder) in enumerate(values):
            bx=left+(i%2)*(card_w+gap); by=top+(i//2)*(card_h+gap)
            tile=pygame.Rect(bx,by,card_w,card_h); pygame.draw.rect(screen,(9,23,34),tile,border_radius=9); pygame.draw.rect(screen,BORDER,tile,1,border_radius=9)
            screen.blit(F17.render(name,True,ACCENT),(bx+18,by+15))
            touch_value('COUNT RATE',f'{float(power or 0):+.0f}/s',bx+18,by+53,GREEN if fresh('enc_m1',5) else RED,card_w//2-24)
            touch_value('ENCODER',str(encoder),bx+card_w//2,by+53,WHITE,card_w//2-18)
        if side_w:
            sx=left+grid_w+gap
            touch_value('DRIVE MODE',str(DATA.get('steer_mode','MANUAL')),sx,rect.y+130,ACCENT)
            touch_value('ODOMETRY',f"X {DATA.get('pos_x',0) or 0:+.2f}  Y {DATA.get('pos_y',0) or 0:+.2f}",sx,rect.y+205)
            touch_value('HEADING',f"{DATA.get('heading',0) or 0:.1f} deg",sx,rect.y+280)
            hud_label('Touch driving is safety-locked. Use remote or web drive controls.',sx,rect.y+360,YELLOW,F13,side_w-20)
    elif ACTIVE_TAB=='MAP':
        screen.blit(F30.render('MAPPING & AUTONOMY',True,WHITE),(rect.x+34,rect.y+65))
        touch_value('MISSION',str(DATA.get('mission_status','STOPPED'))[:60],rect.x+35,rect.y+125,ACCENT,700)
        touch_value('POSITION',f"X {DATA.get('pos_x',0) or 0:+.2f} m   Y {DATA.get('pos_y',0) or 0:+.2f} m",rect.x+35,rect.y+205)
        touch_value('GPS',f"{int(DATA.get('gps_sats',0) or 0)} satellites",rect.x+35,rect.y+285,YELLOW if (DATA.get('gps_sats',0) or 0)<4 else GREEN)
        bx=rect.x+850; by=rect.y+120
        touch_button('set_home',pygame.Rect(bx,by,360,78),'SET HOME',GREEN)
        touch_button('start_mapping',pygame.Rect(bx+380,by,360,78),'START MAPPING',YELLOW,True,'HOLD 1.2 SEC')
        touch_button('return_home',pygame.Rect(bx,by+100,360,78),'RETURN HOME',YELLOW,True,'HOLD 1.2 SEC')
        touch_button('stop_mapping',pygame.Rect(bx+380,by+100,360,78),'STOP & SAVE MAP',RED)
        hud_label('Live map visualization remains available through Foxglove; this screen provides safe touch mission control.',rect.x+35,rect.bottom-70,DIM,F14,rect.w-70)
    elif ACTIVE_TAB=='VOICE':
        screen.blit(F30.render('ATLAS VOICE + LLM',True,WHITE),(rect.x+34,rect.y+65))
        state=str(DATA.get('agent_state','STARTING')); state_color=GREEN if state=='IDLE' else (ACCENT if state in ('LISTENING','THINKING','SPEAKING') else YELLOW)
        touch_value('STATE',state,rect.x+35,rect.y+125,state_color,300)
        touch_value('MODE',str(DATA.get('voice_mode','AUTO ENGLISH + HINDI')),rect.x+390,rect.y+125,ACCENT,500)
        touch_value('CLOUD',str(DATA.get('voice_cloud','--')),rect.x+940,rect.y+125,WHITE,500)
        cards=[
            ('HEARD',str(DATA.get('voice_transcript','Say Hey ATLAS'))),
            ('INTENDED ACTION',str(DATA.get('agent_action','NONE'))),
            ('CONFIRMATION',str(DATA.get('voice_confirmation','Motion commands require confirmation'))),
            ('ATLAS REPLY',str(DATA.get('voice_response','Waiting for a command'))),
        ]
        yy=rect.y+235
        for label,value in cards:
            box=pygame.Rect(rect.x+34,yy,rect.w-68,92)
            pygame.draw.rect(screen,(9,23,34),box,border_radius=9); pygame.draw.rect(screen,BORDER,box,1,border_radius=9)
            hud_label(label,box.x+18,box.y+13,ACCENT,F13,240)
            hud_label(value[:150],box.x+18,box.y+44,WHITE,F17,box.w-36)
            yy+=108
        hud_label('Movement requires: command, then CONFIRM within 30 seconds. STOP is always immediate.',rect.x+35,rect.bottom-60,YELLOW,F14,rect.w-70)

def draw_touch_nav():
    y=H-90
    pygame.draw.rect(screen,(6,17,27),(0,y,W,90))
    pygame.draw.line(screen,BORDER,(0,y),(W,y),1)
    labels=['OVERVIEW','DRIVE','MAP','SENSORS','VOICE','DIAGNOSTICS']; gap=8; margin=12
    bw=(W-2*margin-gap*(len(labels)-1))//len(labels)
    for i,label in enumerate(labels):
        touch_button('tab:'+label,pygame.Rect(margin+i*(bw+gap),y+10,bw,68),label,ACCENT,selected=ACTIVE_TAB==label)

def draw_touch_dashboard():
    global _ip_ts, _net, TOUCH_AREAS
    TOUCH_AREAS={}
    if time.monotonic()-_ip_ts>10:
        _net=net_status(); _ip_ts=time.monotonic()
    screen.fill(BG); draw_touch_header()
    if ACTIVE_TAB=='OVERVIEW':
        top_y=76; top_h=430; gap=10; margin=12
        cam_w=670; radar_w=530; power_w=W-2*margin-2*gap-cam_w-radar_w
        draw_touch_camera(pygame.Rect(margin,top_y,cam_w,top_h))
        radar_rect=pygame.Rect(margin+cam_w+gap,top_y,radar_w,top_h)
        draw_touch_awareness(radar_rect)
        draw_touch_power(pygame.Rect(margin+cam_w+gap+radar_w+gap,top_y,power_w,top_h))
        draw_touch_middle(518,240)
        draw_touch_health(770,H-770-102)
    else:
        draw_touch_tab_page()
    draw_touch_nav()
    text,at,color=TOAST
    if time.monotonic()-at<5:
        surf=F14.render(text,True,color); box=surf.get_rect(center=(W//2,H-102))
        pygame.draw.rect(screen,(3,12,20),box.inflate(32,18),border_radius=9)
        pygame.draw.rect(screen,color,box.inflate(32,18),1,border_radius=9)
        screen.blit(surf,box)

def touch_position(event):
    if event.type in (pygame.FINGERDOWN, pygame.FINGERUP):
        return int(event.x*W), int(event.y*H)
    return event.pos

def handle_touch_event(event):
    global TOUCH_DOWN, TOUCH_DOWN_AT, TOUCH_LAST_ACTION
    down=event.type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN)
    up=event.type in (pygame.MOUSEBUTTONUP, pygame.FINGERUP)
    if not (down or up): return
    pos=touch_position(event)
    if down:
        for key,(rect,long_press) in TOUCH_AREAS.items():
            if rect.collidepoint(pos):
                TOUCH_DOWN=key; TOUCH_DOWN_AT=time.monotonic(); return
    if up and TOUCH_DOWN:
        key=TOUCH_DOWN; TOUCH_DOWN=None
        area=TOUCH_AREAS.get(key)
        if not area or not area[0].collidepoint(pos): return
        held=time.monotonic()-TOUCH_DOWN_AT
        if area[1] and held<1.2:
            set_toast('Hold for 1.2 seconds to confirm',YELLOW); return
        now=time.monotonic()
        if now-TOUCH_LAST_ACTION<0.18: return
        TOUCH_LAST_ACTION=now; do_touch_action(key)
while True:
    pygame.key.stop_text_input()
    for ev in pygame.event.get():
        if ev.type == pygame.QUIT:
            sys.exit()
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            sys.exit()
        handle_touch_event(ev)

    draw_touch_dashboard()
    pygame.display.flip()
    clock.tick(12)
    continue

    screen.fill(BG)
    if False and W >= 1200 and H >= 700:
        m, g = 10, 10
        top_h = int(H * 0.58)
        cam_w = int(W * 0.60)
        right_x = m + cam_w + g
        right_w = W - right_x - m
        draw_camera_block(m, m, cam_w, top_h)
        power_h = int((top_h - g) * 0.56)
        draw_power_block(right_x, m, right_w, power_h)
        draw_attitude_block(right_x, m + power_h + g, right_w, top_h - power_h - g)

        by = m + top_h + g
        bh = H - by - m
        radar_w = int(W * 0.22)
        motor_w = int(W * 0.22)
        range_w = int(W * 0.27)
        comm_w = W - (m * 2 + g * 3 + radar_w + motor_w + range_w)
        x0 = m
        draw_radar_block(x0, by, radar_w, bh)
        x0 += radar_w + g
        draw_motors_block(x0, by, motor_w, bh)
        x0 += motor_w + g
        draw_range_block(x0, by, range_w, bh)
        x0 += range_w + g
        draw_comms_block(x0, by, comm_w, bh)
    elif H >= 700:
        draw_hud_10inch()
    else:
        draw_camera_block(8, 8, 600, 340)
        draw_power_block(616, 8, 400, 188)
        draw_attitude_block(616, 204, 400, 144)
        draw_radar_block(8, 360, 216, 232)
        draw_motors_block(232, 360, 224, 232)
        draw_range_block(464, 360, 220, 232)
        draw_comms_block(692, 360, 324, 232)

    pygame.display.flip()
    clock.tick(4)

pygame.quit()
