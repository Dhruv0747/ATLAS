#!/usr/bin/env python3
"""Face-first camera tracker. Never publishes rover velocity."""
import json
import time

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import Bool, Int32, String


class CameraTracker(Node):
    def __init__(self):
        super().__init__('atlas_camera_tracker')
        self.enabled = True
        self.pan = 1300
        self.tilt = 2500
        self.last_move = 0.0
        self.last_face = 0.0
        self.last_face_scan = 0.0
        cascade_path = '/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml'
        self.face_detector = cv2.CascadeClassifier(cascade_path)
        if self.face_detector.empty():
            raise RuntimeError('OpenCV face cascade could not be loaded')
        self.status = self.create_publisher(String, '/atlas/camera_tracking/status', 10)
        self.face_pub = self.create_publisher(String, '/camera/faces/json', 10)
        self.pan_pub = self.create_publisher(Int32, '/camera/bottom_servo_cmd_us', 10)
        self.tilt_pub = self.create_publisher(Int32, '/camera/second_servo_cmd_us', 10)
        self.create_subscription(Bool, '/atlas/camera_tracking/enabled', self.enable_cb, 10)
        self.create_subscription(String, '/camera/detections/json', self.person_cb, 10)
        self.create_subscription(CompressedImage, '/camera/image_raw/compressed', self.face_cb, 1)
        self.create_subscription(Int32, '/camera/bottom_servo_us', lambda m: setattr(self, 'pan', m.data), 10)
        self.create_subscription(Int32, '/camera/second_servo_us', lambda m: setattr(self, 'tilt', m.data), 10)
        self.status.publish(String(data='ON: face-first camera tracking ready'))

    def enable_cb(self, msg):
        self.enabled = bool(msg.data)
        text = 'ON: tracking face; person fallback enabled' if self.enabled else 'OFF: camera tracking stopped'
        self.status.publish(String(data=text))

    def move_to(self, cx, cy, width, height, source):
        if time.monotonic() - self.last_move < 0.22:
            return
        ex = cx - width / 2
        ey = cy - height / 2
        moved = False
        if abs(ex) > width * 0.09:
            self.pan = max(700, min(2300, int(self.pan + (70 if ex > 0 else -70))))
            self.pan_pub.publish(Int32(data=self.pan)); moved = True
        if abs(ey) > height * 0.10:
            # Larger pulse physically tilts this ATLAS bracket upward.
            self.tilt = max(500, min(2500, int(self.tilt + (-65 if ey > 0 else 65))))
            self.tilt_pub.publish(Int32(data=self.tilt)); moved = True
        if moved:
            self.last_move = time.monotonic()
        self.status.publish(String(data=f'TRACKING {source} pan={self.pan} tilt={self.tilt}'))

    def face_cb(self, msg):
        if not self.enabled or time.monotonic() - self.last_face_scan < 0.18:
            return
        self.last_face_scan = time.monotonic()
        try:
            frame = cv2.imdecode(np.frombuffer(msg.data, np.uint8), cv2.IMREAD_GRAYSCALE)
            if frame is None:
                return
            small = cv2.resize(frame, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
            small = cv2.equalizeHist(small)
            faces = self.face_detector.detectMultiScale(
                small, scaleFactor=1.12, minNeighbors=5, minSize=(34, 34))
            payload = []
            for x, y, w, h in faces:
                payload.append({'x': int(x*2), 'y': int(y*2), 'w': int(w*2), 'h': int(h*2)})
            self.face_pub.publish(String(data=json.dumps({'faces': payload})))
            if not payload:
                return
            face = max(payload, key=lambda f: f['w'] * f['h'])
            self.last_face = time.monotonic()
            self.move_to(face['x'] + face['w']/2, face['y'] + face['h']/2,
                         frame.shape[1], frame.shape[0], 'FACE')
        except Exception as exc:
            self.status.publish(String(data=f'FACE TRACK ERROR: {exc}'))

    def person_cb(self, msg):
        if not self.enabled or time.monotonic() - self.last_face < 1.2:
            return
        try:
            data = json.loads(msg.data)
            people = [d for d in data.get('detections', [])
                      if d.get('label') == 'person' and d.get('confidence', 0) >= 0.45]
            if not people:
                self.status.publish(String(data='SEARCHING: no face or person in frame'))
                return
            person = max(people, key=lambda item: item['confidence'])
            self.move_to((person['x1']+person['x2'])/2, (person['y1']+person['y2'])/2,
                         data['width'], data['height'], 'PERSON FALLBACK')
        except Exception as exc:
            self.status.publish(String(data=f'PERSON TRACK ERROR: {exc}'))


def main():
    rclpy.init(); node = CameraTracker()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node(); rclpy.shutdown()


if __name__ == '__main__':
    main()
