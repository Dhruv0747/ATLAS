#!/usr/bin/env python3
"""
Camera driver for the IMX708 (Camera Module 3) on Project ATLAS's Jetson Orin
Nano Super, via NVIDIA Argus over GStreamer + OpenCV.

Deliberately NOT using camera_ros: that package wraps libcamera, which is the
Raspberry Pi camera stack. This board captures through nvarguscamerasrc /
Argus instead, which is the Jetson-native path and is what actually talks to
this sensor's driver (confirmed working via raw GStreamer + OpenCV test).

Publishes:
  /camera/image_raw              sensor_msgs/Image
  /camera/image_raw/compressed   sensor_msgs/CompressedImage
"""
import cv2
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, CompressedImage
from cv_bridge import CvBridge


def build_pipeline(sensor_id, width, height, framerate):
    return (
        f'nvarguscamerasrc sensor-id={sensor_id} ! '
        f'video/x-raw(memory:NVMM),width={width},height={height},'
        f'framerate={framerate}/1 ! '
        f'nvvidconv ! video/x-raw,format=BGRx ! '
        f'videoconvert ! video/x-raw,format=BGR ! '
        f'appsink drop=1 max-buffers=1'
    )


class CameraNode(Node):
    def __init__(self):
        super().__init__('atlas_camera_node')

        self.declare_parameter('sensor_id', 0)
        self.declare_parameter('width', 1280)
        self.declare_parameter('height', 720)
        self.declare_parameter('framerate', 15)
        self.declare_parameter('frame_id', 'camera_link')
        self.declare_parameter('jpeg_quality', 70)

        self.frame_id = self.get_parameter('frame_id').value
        self.jpeg_quality = self.get_parameter('jpeg_quality').value

        pipeline = build_pipeline(
            self.get_parameter('sensor_id').value,
            self.get_parameter('width').value,
            self.get_parameter('height').value,
            self.get_parameter('framerate').value,
        )

        self.bridge = CvBridge()
        self.pub_raw = self.create_publisher(Image, '/camera/image_raw', 1)
        self.pub_compressed = self.create_publisher(
            CompressedImage, '/camera/image_raw/compressed', 1)

        self.cap = None
        self._open(pipeline)

        fps = self.get_parameter('framerate').value
        self.timer = self.create_timer(1.0 / max(fps, 1), self._tick)
        self.get_logger().info(f'Camera node started, pipeline: {pipeline}')

    def _open(self, pipeline):
        self.cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        if not self.cap.isOpened():
            self.get_logger().error('Failed to open Argus camera pipeline')
            self.cap = None

    def _tick(self):
        if self.cap is None:
            return
        ok, frame = self.cap.read()
        if not ok:
            self.get_logger().warn('Frame read failed', throttle_duration_sec=5.0)
            return

        stamp = self.get_clock().now().to_msg()

        img_msg = self.bridge.cv2_to_imgmsg(frame, encoding='bgr8')
        img_msg.header.stamp = stamp
        img_msg.header.frame_id = self.frame_id
        self.pub_raw.publish(img_msg)

        ok_enc, buf = cv2.imencode(
            '.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
        if ok_enc:
            comp_msg = CompressedImage()
            comp_msg.header.stamp = stamp
            comp_msg.header.frame_id = self.frame_id
            comp_msg.format = 'jpeg'
            comp_msg.data = buf.tobytes()
            self.pub_compressed.publish(comp_msg)

    def destroy_node(self):
        if self.cap is not None:
            self.cap.release()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = CameraNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
