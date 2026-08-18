#!/usr/bin/env python3
"""Publishes camera images with YOLO detection boxes for Foxglove."""
import sys, time, json
sys.path.insert(0, "/home/jetson/project_atlas/scripts")
import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import Bool, String
from trt_yolo_detector import TensorRTYOLO

ENGINE = "/home/jetson/project_atlas/scripts/yolov8n_fp16.engine"
COCO = ["person","bicycle","car","motorcycle","airplane","bus","train","truck","boat","traffic light","fire hydrant","stop sign","parking meter","bench","bird","cat","dog","horse","sheep","cow","elephant","bear","zebra","giraffe","backpack","umbrella","handbag","tie","suitcase","frisbee","skis","snowboard","sports ball","kite","baseball bat","baseball glove","skateboard","surfboard","tennis racket","bottle","wine glass","cup","fork","knife","spoon","bowl","banana","apple","sandwich","orange","broccoli","carrot","hot dog","pizza","donut","cake","chair","couch","potted plant","bed","dining table","toilet","tv","laptop","mouse","remote","keyboard","cell phone","microwave","oven","toaster","sink","refrigerator","book","clock","vase","scissors","teddy bear","hair drier","toothbrush"]

class Annotator(Node):
    def __init__(self):
        super().__init__("ai_annotator")
        self.det = TensorRTYOLO(ENGINE)
        self.pub = self.create_publisher(CompressedImage, "/camera/detections/compressed", 10)
        self.detection_pub = self.create_publisher(String, "/camera/detections/json", 10)
        self.enabled = False
        self.create_subscription(Bool, "/atlas/ai_enabled", self.enable_cb, 10)
        self.create_subscription(CompressedImage, "/camera/image_raw/compressed", self.cb, qos_profile_sensor_data)
        self.last = 0.0
        self.get_logger().info("AI annotator ready")

    def enable_cb(self, msg):
        self.enabled = bool(msg.data)
        self.get_logger().info("AI object detection %s" % ("enabled" if self.enabled else "disabled"))

    def cb(self, msg):
        if not self.enabled:
            return
        now = time.time()
        # Keep Foxglove responsive on Wi-Fi/Tailscale while retaining a useful
        # real-time annotated view. The raw camera remains the faster stream.
        if now - self.last < 0.25:
            return
        self.last = now
        img = cv2.imdecode(np.frombuffer(msg.data, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return
        try:
            dets = self.det.infer(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        except Exception as exc:
            self.get_logger().warning(f"infer failed: {exc}")
            return
        structured = []
        for x1, y1, x2, y2, cid, conf in dets:
            name = COCO[cid] if cid < len(COCO) else str(cid)
            structured.append({"label": name, "confidence": round(float(conf), 3),
                               "x1": int(x1), "y1": int(y1), "x2": int(x2), "y2": int(y2)})
            label = f"{name} {conf*100:.0f}%"
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.rectangle(img, (x1, max(0, y1-20)), (x1 + 9*len(label), y1), (0, 255, 0), -1)
            cv2.putText(img, label, (x1+2, y1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1)
        out = CompressedImage()
        out.header = msg.header
        out.format = "jpeg"
        out.data = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 60])[1].tobytes()
        self.pub.publish(out)
        self.detection_pub.publish(String(data=json.dumps({"width": int(img.shape[1]), "height": int(img.shape[0]), "detections": structured})))

def main():
    rclpy.init()
    node = Annotator()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

if __name__ == "__main__":
    main()
