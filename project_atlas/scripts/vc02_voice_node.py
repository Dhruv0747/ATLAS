#!/usr/bin/env python3
"""Project ATLAS VC-02 offline speech bridge.

Safe behavior:
- Never opens known rover ports: Yahboom, RPLidar, Arduino, SIMCOM 5G.
- Waits for a new/unknown USB serial adapter.
- Publishes raw voice events and optional safe /cmd_vel pulses.
"""
import glob
import json
import os
import re
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Bool, String

try:
    import serial
except Exception as exc:
    serial = None

BAUDS = [115200, 9600, 57600, 38400]
DENY_LINKS = ['/dev/yahboom', '/dev/rplidar']
DENY_KEYWORDS = ['Arduino_UNO', 'SIMCOM', 'Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001']

COMMANDS = {
    'stop': ('stop', 0.0, 0.0),
    'emergency stop': ('stop', 0.0, 0.0),
    'halt': ('stop', 0.0, 0.0),
    'forward': ('forward', 0.45, 0.0),
    'go forward': ('forward', 0.45, 0.0),
    'back': ('back', -0.35, 0.0),
    'backward': ('back', -0.35, 0.0),
    'left': ('left', 0.0, 0.85),
    'turn left': ('left', 0.0, 0.85),
    'right': ('right', 0.0, -0.85),
    'turn right': ('right', 0.0, -0.85),
}
# Common numeric IDs. We will refine after seeing your module's actual output.
ID_COMMANDS = {
    0: ('stop', 0.0, 0.0),
    1: ('forward', 0.45, 0.0),
    2: ('back', -0.35, 0.0),
    3: ('left', 0.0, 0.85),
    4: ('right', 0.0, -0.85),
}


def real(path):
    try:
        return os.path.realpath(path)
    except Exception:
        return path


class VC02Voice(Node):
    def __init__(self):
        super().__init__('vc02_voice')
        self.port = None
        self.ser = None
        self.enabled = True
        self.last_event = '--'
        self.last_raw = ''
        self.last_seen = 0.0
        self.pub_status = self.create_publisher(String, '/voice/vc02/status', 10)
        self.pub_event = self.create_publisher(String, '/voice/vc02/event', 10)
        self.pub_raw = self.create_publisher(String, '/voice/vc02/raw', 10)
        self.pub_enabled = self.create_publisher(Bool, '/voice/vc02/enabled', 10)
        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.create_timer(0.15, self.tick)
        self.get_logger().info('VC-02 voice bridge active: waiting for unknown USB serial device')

    def known_targets(self):
        out = set()
        for p in DENY_LINKS:
            if os.path.exists(p):
                out.add(real(p))
        return out

    def candidate_ports(self):
        forced = os.environ.get('VC02_PORT', '').strip()
        if forced:
            return [forced]
        denied = self.known_targets()
        ports = []
        byid = glob.glob('/dev/serial/by-id/*')
        for p in byid:
            if any(k in p for k in DENY_KEYWORDS):
                continue
            rp = real(p)
            if rp not in denied:
                ports.append(p)
        for p in sorted(glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')):
            rp = real(p)
            if rp in denied:
                continue
            # Keep Arduino and 5G protected even if symlink is missing.
            if p == '/dev/ttyACM0' or p in ['/dev/ttyUSB0', '/dev/ttyUSB1', '/dev/ttyUSB3', '/dev/ttyUSB4', '/dev/ttyUSB5']:
                continue
            ports.append(p)
        return list(dict.fromkeys(ports))

    def connect(self):
        if serial is None:
            self.pub_status.publish(String(data='VC02_ERROR pyserial_missing'))
            return False
        for port in self.candidate_ports():
            for baud in BAUDS:
                try:
                    self.ser = serial.Serial(port, baudrate=baud, timeout=0.02)
                    self.port = port
                    self.pub_status.publish(String(data=f'VC02_OK port={port} baud={baud}'))
                    self.get_logger().info(f'VC-02 connected on {port} baud={baud}')
                    return True
                except Exception:
                    pass
        self.pub_status.publish(String(data='VC02_OFFLINE connect_usb_or_set_VC02_PORT'))
        return False

    def publish_cmd(self, name, lin, ang):
        msg = Twist()
        msg.linear.x = float(lin)
        msg.angular.z = float(ang)
        # Short safe pulse, then stop. User can repeat command by voice.
        end = time.time() + (0.8 if name != 'stop' else 0.05)
        while time.time() < end:
            self.cmd_pub.publish(msg)
            time.sleep(0.08)
        stop = Twist()
        self.cmd_pub.publish(stop)

    def parse_event(self, raw):
        text = raw.strip().lower()
        text = re.sub(r'[^a-z0-9 _:-]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        for key, cmd in COMMANDS.items():
            if key in text:
                return cmd
        nums = re.findall(r'\b\d+\b', text)
        if nums:
            n = int(nums[-1])
            if n in ID_COMMANDS:
                return ID_COMMANDS[n]
        # Hex frame fallback: use last byte as command ID when present.
        bs = raw.encode('latin1', 'ignore') if isinstance(raw, str) else raw
        if bs:
            n = bs[-1]
            if n in ID_COMMANDS:
                return ID_COMMANDS[n]
        return ('unknown', 0.0, 0.0)

    def read_raw(self):
        data = b''
        try:
            data = self.ser.readline()
            if not data:
                data = self.ser.read(32)
        except Exception as exc:
            self.pub_status.publish(String(data=f'VC02_ERROR read {exc}'))
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None
            self.port = None
            return ''
        if not data:
            return ''
        try:
            return data.decode('utf-8', 'ignore')
        except Exception:
            return 'HEX ' + data.hex(' ')

    def tick(self):
        if self.ser is None:
            self.connect()
            self.pub_enabled.publish(Bool(data=self.enabled))
            return
        raw = self.read_raw()
        if not raw:
            age = time.time() - self.last_seen if self.last_seen else 999.0
            self.pub_status.publish(String(data=f'VC02_OK port={self.port} waiting last={age:.1f}s'))
            self.pub_enabled.publish(Bool(data=self.enabled))
            return
        self.last_seen = time.time()
        self.last_raw = raw.strip()
        name, lin, ang = self.parse_event(raw)
        event = {'command': name, 'linear': lin, 'angular': ang, 'raw': self.last_raw, 'enabled': self.enabled}
        self.pub_raw.publish(String(data=self.last_raw))
        self.pub_event.publish(String(data=json.dumps(event, separators=(',', ':'))))
        self.pub_status.publish(String(data=f'VC02_EVENT {name} raw={self.last_raw[:40]}'))
        if self.enabled and name != 'unknown':
            self.publish_cmd(name, lin, ang)


def main():
    rclpy.init()
    node = VC02Voice()
    try:
        rclpy.spin(node)
    finally:
        try:
            if node.ser:
                node.ser.close()
        except Exception:
            pass
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()