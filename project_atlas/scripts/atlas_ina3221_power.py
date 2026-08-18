#!/usr/bin/env python3
"""Publish Jetson INA3221 rail telemetry from the kernel hwmon interface."""
import glob, json, os
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32, String

class Ina3221Power(Node):
    def __init__(self):
        super().__init__("atlas_ina3221_power")
        self.root = self._find_hwmon()
        names = ("input_voltage", "input_current", "input_power", "cpu_gpu_voltage",
                 "cpu_gpu_current", "cpu_gpu_power", "soc_voltage", "soc_current",
                 "soc_power", "total_current")
        self.pubs = {n: self.create_publisher(Float32, f"/jetson/power/{n}", 10) for n in names}
        self.status_pub = self.create_publisher(String, "/jetson/power/status", 10)
        self.json_pub = self.create_publisher(String, "/jetson/power/json", 10)
        self.create_timer(1.0, self.sample)
        self.get_logger().info(f"INA3221 telemetry using {self.root}")

    @staticmethod
    def _find_hwmon():
        for root in glob.glob("/sys/class/hwmon/hwmon*"):
            try:
                with open(os.path.join(root, "name"), encoding="ascii") as stream:
                    if stream.read().strip() == "ina3221": return root
            except OSError: pass
        raise RuntimeError("INA3221 hwmon device not found")

    def _value(self, filename):
        with open(os.path.join(self.root, filename), encoding="ascii") as stream:
            return float(stream.read().strip()) / 1000.0

    def sample(self):
        try:
            vin, iin = self._value("in1_input"), self._value("curr1_input")
            vcpu, icpu = self._value("in2_input"), self._value("curr2_input")
            vsoc, isoc = self._value("in3_input"), self._value("curr3_input")
            try: total = self._value("curr4_input")
            except OSError: total = iin + icpu + isoc
            values = {"input_voltage":vin,"input_current":iin,"input_power":vin*iin,
                      "cpu_gpu_voltage":vcpu,"cpu_gpu_current":icpu,"cpu_gpu_power":vcpu*icpu,
                      "soc_voltage":vsoc,"soc_current":isoc,"soc_power":vsoc*isoc,
                      "total_current":total}
            for name, value in values.items(): self.pubs[name].publish(Float32(data=float(value)))
            warning = "UNDERVOLTAGE" if vin < 4.65 else "HIGH_POWER" if values["input_power"] > 20 else "OK"
            self.json_pub.publish(String(data=json.dumps({"ok":True,"source":"ina3221","warning":warning,**values}, separators=(",",":"))))
            self.status_pub.publish(String(data=f"INA3221_{warning} {vin:.3f}V {iin:.3f}A {values['input_power']:.2f}W"))
        except (OSError, ValueError) as exc:
            self.status_pub.publish(String(data=f"INA3221_OFFLINE error={exc}"))

def main():
    rclpy.init(); node = Ina3221Power()
    try: rclpy.spin(node)
    finally: node.destroy_node(); rclpy.shutdown()
if __name__ == "__main__": main()
