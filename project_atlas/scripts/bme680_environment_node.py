#!/usr/bin/env python3
"""Project ATLAS BME680 environmental publisher (I2C bus 7, address 0x77)."""

import json
import math
import time

import bme680
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from smbus2 import SMBus
from std_msgs.msg import Float32, String

BUS_ID = 7
ADDRESS = 0x77


class Bme680Environment(Node):
    def __init__(self):
        super().__init__("bme680_environment")
        self.pubs = {
            "temperature": self.create_publisher(Float32, "/environment/outside_temperature_c", 10),
            "humidity": self.create_publisher(Float32, "/environment/outside_humidity_pct", 10),
            "pressure": self.create_publisher(Float32, "/environment/pressure_hpa", 10),
            "gas": self.create_publisher(Float32, "/environment/gas_resistance_ohm", 10),
            "iaq": self.create_publisher(Float32, "/environment/iaq", 10),
            "eco2": self.create_publisher(Float32, "/environment/eco2_ppm", 10),
            "status": self.create_publisher(String, "/environment/outside_status", 10),
            "json": self.create_publisher(String, "/environment/bme680/json", 10),
        }
        self.bus = None
        self.sensor = None
        self.gas_baseline = None
        self.last_poll = 0.0
        self.create_timer(1.0, self.poll)
        self.get_logger().info(f"BME680 starting: bus={BUS_ID} addr=0x{ADDRESS:02x}")

    def connect(self):
        self.close_sensor()
        self.bus = SMBus(BUS_ID)
        self.sensor = bme680.BME680(i2c_addr=ADDRESS, i2c_device=self.bus)
        self.sensor.set_humidity_oversample(bme680.OS_2X)
        self.sensor.set_pressure_oversample(bme680.OS_4X)
        self.sensor.set_temperature_oversample(bme680.OS_8X)
        self.sensor.set_filter(bme680.FILTER_SIZE_3)
        self.sensor.set_gas_status(bme680.ENABLE_GAS_MEAS)
        self.sensor.set_gas_heater_temperature(320)
        self.sensor.set_gas_heater_duration(150)
        self.sensor.select_gas_heater_profile(0)

    def close_sensor(self):
        self.sensor = None
        if self.bus is not None:
            try:
                self.bus.close()
            except Exception:
                pass
        self.bus = None

    @staticmethod
    def quality(iaq):
        if iaq <= 50:
            return "EXCELLENT"
        if iaq <= 100:
            return "GOOD"
        if iaq <= 150:
            return "MODERATE"
        if iaq <= 200:
            return "POOR"
        if iaq <= 300:
            return "UNHEALTHY"
        return "HAZARDOUS"

    def estimate_air_quality(self, humidity, gas, stable):
        if not stable or gas <= 0:
            return math.nan, math.nan, "WARMING"
        # Maintain a slow local clean-air reference. This is a transparent
        # fallback IAQ estimate, not Bosch BSEC and not a direct CO2 reading.
        if self.gas_baseline is None:
            self.gas_baseline = gas
        elif gas > self.gas_baseline:
            self.gas_baseline = 0.995 * self.gas_baseline + 0.005 * gas
        else:
            self.gas_baseline = 0.9995 * self.gas_baseline + 0.0005 * gas
        gas_score = min(75.0, max(0.0, 75.0 * gas / max(1.0, self.gas_baseline)))
        humidity_score = max(0.0, 25.0 - abs(humidity - 40.0) * 0.625)
        iaq = max(0.0, min(500.0, 500.0 - 5.0 * (gas_score + humidity_score)))
        eco2 = max(400.0, min(5000.0, 400.0 + max(0.0, iaq - 25.0) * 8.0))
        return iaq, eco2, self.quality(iaq)

    def poll(self):
        try:
            if self.sensor is None:
                self.connect()
            if not self.sensor.get_sensor_data():
                return
            data = self.sensor.data
            iaq, eco2, label = self.estimate_air_quality(
                float(data.humidity), float(data.gas_resistance), bool(data.heat_stable)
            )
            values = {
                "ok": True,
                "address": f"0x{ADDRESS:02x}",
                "bus": BUS_ID,
                "temperature_c": round(float(data.temperature), 2),
                "humidity_pct": round(float(data.humidity), 1),
                "pressure_hpa": round(float(data.pressure), 1),
                "gas_resistance_ohm": round(float(data.gas_resistance), 0),
                "heat_stable": bool(data.heat_stable),
                "iaq_estimate": None if math.isnan(iaq) else round(iaq, 1),
                "eco2_estimate_ppm": None if math.isnan(eco2) else round(eco2, 0),
                "quality": label,
                "note": "IAQ/eCO2 are VOC-derived estimates; eCO2 is not direct CO2",
            }
            self.pubs["temperature"].publish(Float32(data=float(data.temperature)))
            self.pubs["humidity"].publish(Float32(data=float(data.humidity)))
            self.pubs["pressure"].publish(Float32(data=float(data.pressure)))
            self.pubs["gas"].publish(Float32(data=float(data.gas_resistance)))
            if not math.isnan(iaq):
                self.pubs["iaq"].publish(Float32(data=float(iaq)))
                self.pubs["eco2"].publish(Float32(data=float(eco2)))
            status = (
                f"BME680_{label} addr=0x{ADDRESS:02x} T={data.temperature:.1f}C "
                f"RH={data.humidity:.0f}% P={data.pressure:.1f}hPa"
            )
            self.pubs["status"].publish(String(data=status))
            self.pubs["json"].publish(String(data=json.dumps(values, separators=(",", ":"))))
        except Exception as error:
            self.pubs["status"].publish(String(data=f"BME680_OFFLINE error={error}"))
            self.get_logger().error(f"BME680 read failed: {error}")
            self.close_sensor()

    def destroy_node(self):
        self.close_sensor()
        super().destroy_node()


def main():
    rclpy.init()
    node = Bme680Environment()
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
