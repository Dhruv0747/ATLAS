#!/usr/bin/env python3
"""Rover autonomous explorer with camera object detection (OpenCV DNN + YOLOv8n ONNX).

Usage:
  python3 rover_explore_camera.py                  # run forever
  python3 rover_explore_camera.py --duration 300   # run 5 minutes
  python3 rover_explore_camera.py --no-camera      # lidar-only fallback
"""

import argparse
import math
import threading
import time
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from sensor_msgs.msg import Image, LaserScan
from std_msgs.msg import String

# -- Lidar navigation constants -----------------------------------------------
SPD  = 0.20   # m/s forward speed
TRN  = 0.60   # rad/s turn speed
DIST = 0.70   # metres -- obstacle stop distance
ARC  = 50     # degrees -- front arc to check for obstacles
INT  = 12     # seconds between planned exploratory turns

# -- Camera detection constants -----------------------------------------------
MODEL_PATH   = '/home/jetson/project_atlas/scripts/yolov8n.onnx'
CAM_DEVICE   = 0      # /dev/video0 (CSI camera via libcamera v4l2 compat)
DET_INTERVAL = 0.5    # seconds between detection cycles
CONF_THRESH  = 0.45   # minimum detection confidence
NMS_THRESH   = 0.50   # NMS IOU threshold
INP_SIZE     = 640    # YOLOv8 input image size
STOP_SECS    = 3.0    # seconds to pause when a stop-class is detected

# Rover stops for this many seconds when it sees any of these objects
STOP_CLASSES = {'person', 'cat', 'dog'}

COCO_NAMES = [
    'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train',
    'truck', 'boat', 'traffic light', 'fire hydrant', 'stop sign',
    'parking meter', 'bench', 'bird', 'cat', 'dog', 'horse', 'sheep', 'cow',
    'elephant', 'bear', 'zebra', 'giraffe', 'backpack', 'umbrella', 'handbag',
    'tie', 'suitcase', 'frisbee', 'skis', 'snowboard', 'sports ball', 'kite',
    'baseball bat', 'baseball glove', 'skateboard', 'surfboard',
    'tennis racket', 'bottle', 'wine glass', 'cup', 'fork', 'knife', 'spoon',
    'bowl', 'banana', 'apple', 'sandwich', 'orange', 'broccoli', 'carrot',
    'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch', 'potted plant',
    'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse', 'remote',
    'keyboard', 'cell phone', 'microwave', 'oven', 'toaster', 'sink',
    'refrigerator', 'book', 'clock', 'vase', 'scissors', 'teddy bear',
    'hair drier', 'toothbrush',
]


class CameraDetector:
    """Runs YOLOv8n ONNX detection in a background thread via OpenCV DNN.

    No PyTorch required -- uses cv2.dnn only.
    """

    def __init__(self):
        import cv2
        self.cv2 = cv2

        print('[CAM] Loading YOLOv8n ONNX model...')
        self.net = cv2.dnn.readNetFromONNX(MODEL_PATH)
        print('[CAM] Model loaded OK')

        self.cap = cv2.VideoCapture(CAM_DEVICE)
        if not self.cap.isOpened():
            raise RuntimeError(f'Cannot open camera {CAM_DEVICE}')
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        print('[CAM] Camera opened OK')

        self._lock = threading.Lock()
        self._detections = []   # list of (class_name, confidence)
        self._frame = None      # latest annotated frame for Foxglove
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print('[CAM] Detection thread started')

    def _loop(self):
        while self._running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.1)
                continue
            try:
                dets, annotated = self._detect(frame)
            except Exception as e:
                print(f'[CAM] Detection error: {e}')
                dets, annotated = [], frame
            with self._lock:
                self._detections = dets
                self._frame = annotated
            if dets:
                labels = ', '.join(f'{n}({c:.2f})' for n, c in dets)
                print(f'[CAM] Detected: {labels}')
            time.sleep(DET_INTERVAL)

    def _detect(self, frame):
        """Run YOLOv8 inference. Returns (detections, annotated_frame)."""
        cv2 = self.cv2
        h, w = frame.shape[:2]
        annotated = frame.copy()

        blob = cv2.dnn.blobFromImage(
            frame, 1.0 / 255.0, (INP_SIZE, INP_SIZE), swapRB=True, crop=False
        )
        self.net.setInput(blob)
        out = self.net.forward()   # shape: (1, 84, 8400)

        # YOLOv8 ONNX: cols 0-3 = cx,cy,bw,bh (norm to INP_SIZE), cols 4-83 = class scores
        out = out[0].T             # -> (8400, 84)

        sx = w / INP_SIZE
        sy = h / INP_SIZE

        raw = []  # (name, conf, x1, y1, x2, y2)
        for row in out:
            scores = row[4:]
            cls_id = int(scores.argmax())
            conf = float(scores[cls_id])
            if conf < CONF_THRESH:
                continue
            cx, cy, bw, bh = float(row[0]), float(row[1]), float(row[2]), float(row[3])
            x1 = int((cx - bw / 2) * sx)
            y1 = int((cy - bh / 2) * sy)
            x2 = int((cx + bw / 2) * sx)
            y2 = int((cy + bh / 2) * sy)
            name = COCO_NAMES[cls_id] if cls_id < len(COCO_NAMES) else str(cls_id)
            raw.append((name, conf, x1, y1, x2, y2))

        # Deduplicate: keep highest confidence per class
        best = {}
        for name, conf, x1, y1, x2, y2 in raw:
            if name not in best or conf > best[name][0]:
                best[name] = (conf, x1, y1, x2, y2)

        # Draw bounding boxes on annotated frame
        for name, (conf, x1, y1, x2, y2) in best.items():
            color = (0, 0, 255) if name in STOP_CLASSES else (0, 255, 0)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            label = f'{name} {conf:.2f}'
            cv2.putText(annotated, label, (x1, max(y1 - 5, 15)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

        dets = [(name, conf) for name, (conf, *_) in best.items()]
        return dets, annotated

    def get_detections(self):
        """Return the most recent detection list (thread-safe)."""
        with self._lock:
            return list(self._detections)

    def get_frame(self):
        """Return the latest annotated frame (thread-safe), or None."""
        with self._lock:
            return self._frame

    def stop(self):
        self._running = False
        self.cap.release()
        print('[CAM] Detector stopped')


class ReactiveExplorer(Node):
    """Lidar-reactive explorer with optional camera safety stop."""

    def __init__(self, duration=0, camera=None):
        super().__init__('reactive_explorer')
        self.pub     = self.create_publisher(Twist, '/cmd_vel', 10)
        self.img_pub = self.create_publisher(Image, '/camera/image_raw', 2)
        self.det_pub = self.create_publisher(String, '/detections', 10)
        self.sub     = self.create_subscription(LaserScan, '/scan', self._cb, 10)
        self.scan    = None
        self.camera  = camera

        self._duration       = duration
        self._start          = time.time()
        self._last_turn      = time.time()
        self._cam_stop_until = 0.0

        self.timer     = self.create_timer(0.1,  self._tick)
        self.img_timer = self.create_timer(0.2,  self._publish_image)   # 5 Hz
        self.get_logger().info(
            f'ReactiveExplorer started | duration={duration}s | '
            f'camera={"yes" if camera else "no"}'
        )

    # -- Lidar callback -------------------------------------------------------
    def _cb(self, msg):
        self.scan = msg

    # -- Angle transform: compensates for 180-degree reversed lidar mount -----
    def _angles(self):
        s = self.scan
        if not s:
            return
        for i, r in enumerate(s.ranges):
            if not (s.range_min < r < s.range_max):
                continue
            angle = s.angle_min + i * s.angle_increment
            angle = angle % (2 * math.pi) - math.pi
            yield angle, r

    def ok(self):
        """True if the forward arc is clear of obstacles."""
        arc = math.radians(ARC)
        for angle, r in self._angles():
            if abs(angle) < arc and r < DIST:
                return False
        return True

    def side(self):
        """Return 'left' or 'right' -- whichever side has more open space."""
        left = right = 0
        for angle, r in self._angles():
            if 0.1 < abs(angle) < math.pi / 2:
                if angle > 0:
                    left += 1
                else:
                    right += 1
        return 'left' if right >= left else 'right'

    def _cmd(self, lin, ang):
        t = Twist()
        t.linear.x  = float(lin)
        t.angular.z = float(ang)
        self.pub.publish(t)

    def _publish_image(self):
        """Publish latest annotated camera frame to /camera/image_raw (for Foxglove)."""
        if self.camera is None:
            return
        frame = self.camera.get_frame()
        if frame is None:
            return
        msg = Image()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'camera'
        msg.height = frame.shape[0]
        msg.width  = frame.shape[1]
        msg.encoding = 'bgr8'
        msg.is_bigendian = False
        msg.step = frame.shape[1] * 3
        msg.data = frame.tobytes()
        self.img_pub.publish(msg)

        # Also publish detection text to /detections
        dets = self.camera.get_detections()
        if dets:
            s = String()
            s.data = ', '.join(f'{n}:{c:.2f}' for n, c in dets)
            self.det_pub.publish(s)

    def _stop_class_seen(self):
        """Return True if camera sees a person, cat, or dog."""
        if self.camera is None:
            return False
        for name, _conf in self.camera.get_detections():
            if name in STOP_CLASSES:
                return True
        return False

    # -- Main control loop (called at 10 Hz) ----------------------------------
    def _tick(self):
        now = time.time()

        # Duration limit
        if self._duration > 0 and (now - self._start) > self._duration:
            self._cmd(0, 0)
            self.get_logger().info('Duration reached -- stopping.')
            rclpy.shutdown()
            return

        # Camera safety stop (count-down)
        if now < self._cam_stop_until:
            self._cmd(0, 0)
            return

        # Trigger new camera stop if something detected
        if self._stop_class_seen():
            remaining = self._cam_stop_until - now
            if remaining <= 0:
                self.get_logger().info(
                    f'OBJECT DETECTED -- stopping for {STOP_SECS:.0f}s'
                )
                self._cam_stop_until = now + STOP_SECS
            self._cmd(0, 0)
            return

        # Lidar not ready yet
        if self.scan is None:
            return

        # Obstacle avoidance
        if not self.ok():
            d = self.side()
            ang = TRN if d == 'left' else -TRN
            self.get_logger().info(f'Obstacle -- turning {d}')
            self._cmd(0.0, ang)
            self._last_turn = now
            return

        # Planned exploratory turn
        if now - self._last_turn > INT:
            self._cmd(0.0, TRN)
            time.sleep(0.5)
            self._last_turn = now
            return

        # Drive forward
        self._cmd(SPD, 0.0)


def main():
    parser = argparse.ArgumentParser(description='Rover explorer with camera')
    parser.add_argument('--duration', type=int, default=0,
                        help='Run duration in seconds (default: 0 = infinite)')
    parser.add_argument('--no-camera', action='store_true',
                        help='Disable camera (lidar-only mode)')
    args = parser.parse_args()

    camera = None
    if not args.no_camera:
        try:
            camera = CameraDetector()
        except Exception as e:
            print(f'[CAM] Warning: camera failed to start: {e}')
            print('[CAM] Continuing in lidar-only mode')

    rclpy.init()
    node = ReactiveExplorer(duration=args.duration, camera=camera)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node._cmd(0.0, 0.0)
        node.destroy_node()
        if camera:
            camera.stop()
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == '__main__':
    main()
