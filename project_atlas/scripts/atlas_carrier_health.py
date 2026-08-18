#!/usr/bin/env python3
"""Publish non-invasive Waveshare JETSON-ORIN-IO-BASE health telemetry."""
import glob, json, os, re, shutil, subprocess
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

def read(path, default=""):
    try:
        with open(path, encoding="utf-8") as stream: return stream.read().strip("\x00\n ")
    except OSError: return default

class CarrierHealth(Node):
    def __init__(self):
        super().__init__("atlas_carrier_health")
        self.json_pub = self.create_publisher(String, "/jetson/carrier/json", 10)
        self.status_pub = self.create_publisher(String, "/jetson/carrier/status", 10)
        self.create_timer(10.0, self.sample)
        self.sample()

    def sample(self):
        disk = shutil.disk_usage("/")
        net = {}
        for path in glob.glob("/sys/class/net/*"):
            name = os.path.basename(path)
            if name == "lo": continue
            net[name] = {"state": read(f"{path}/operstate", "unknown"),
                         "carrier": read(f"{path}/carrier", "0") == "1"}
        try:
            mode = subprocess.check_output(["nvpmodel", "-q"], text=True, timeout=2, stderr=subprocess.DEVNULL).splitlines()[0].replace("NV Power Mode:", "").strip()
        except Exception: mode = "unknown"
        payload = {
            "ok": True,
            "board": "Waveshare JETSON-ORIN-IO-BASE",
            "model": read("/proc/device-tree/model", "Jetson Orin"),
            "power_mode": mode,
            "nvme": {"present": os.path.exists("/dev/nvme0n1"), "model": read("/sys/class/nvme/nvme0/model", "unknown"),
                     "total_gb": round(disk.total/1e9,1), "free_gb": round(disk.free/1e9,1), "used_percent": round(disk.used/disk.total*100,1)},
            "rtc": {"present": os.path.exists("/dev/rtc0")},
            "csi_video_devices": len(glob.glob("/dev/video*")),
            "usb_devices": sum(bool(re.fullmatch(r"\d+-\d+(?:\.\d+)*", os.path.basename(x))) for x in glob.glob("/sys/bus/usb/devices/*")),
            "i2c_buses": len(glob.glob("/dev/i2c-*")),
            "uart_ports": [os.path.basename(x) for x in glob.glob("/dev/ttyTHS*")],
            "can_available": os.path.exists("/sys/class/net/can0"),
            "network": net,
        }
        warning = "NVME_HIGH_USAGE" if payload["nvme"]["used_percent"] > 90 else "OK"
        payload["warning"] = warning
        self.json_pub.publish(String(data=json.dumps(payload, separators=(",",":"))))
        self.status_pub.publish(String(data=f"ORIN_IO_BASE_{warning} {mode} NVME_FREE={payload['nvme']['free_gb']}GB USB={payload['usb_devices']} CSI={payload['csi_video_devices']}"))

def main():
    rclpy.init(); node=CarrierHealth()
    try: rclpy.spin(node)
    finally: node.destroy_node(); rclpy.shutdown()
if __name__ == "__main__": main()
