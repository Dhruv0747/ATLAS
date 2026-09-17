"""Extract small production methods; tests never import ROS or access hardware."""
import ast
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import unittest


def method(filename, cls, name, scope):
    tree = ast.parse(Path(__file__).with_name(filename).read_text(encoding='utf-8'))
    typ = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
    fn = next(n for n in typ.body if isinstance(n, ast.FunctionDef) and n.name == name)
    fn.decorator_list = []
    exec(compile(ast.Module(body=[fn], type_ignores=[]), '<production-method>', 'exec'), scope)
    return scope[name]


class CameraLinkTests(unittest.TestCase):
    def resolve(self, paths, configured):
        # Fake filesystem maps symlinks to physical ports.
        scope = {'HUB_TRANSPORT': 'uno_r4_i2c_hub', 'PORT_FALLBACK_PATTERNS': [],
            'os': SimpleNamespace(path=SimpleNamespace(exists=lambda p:p in paths,
                realpath=lambda p:paths[p])),
            'glob': SimpleNamespace(glob=lambda pattern:[p for p in paths
                if p.startswith('/dev/serial/by-id/usb-Arduino_UNO_R4_WiFi_')])}
        fn = method('ultrasonic_arduino_bridge.py', 'UltrasonicArduinoBridge', 'resolve_port', scope)
        return fn(configured)

    def test_debug_alias_not_accepted(self):
        self.assertEqual(self.resolve({'/dev/atlas-sensor-hub':'/dev/ttyACM1',
            '/dev/serial/by-id/usb-Arduino_UNO_WiFi_R4_CMSIS-DAP_x-if01':'/dev/ttyACM1'},
            '/dev/atlas-sensor-hub'), '')

    def test_unrelated_acm_not_accepted(self):
        self.assertEqual(self.resolve({'/dev/ttyACM0':'/dev/ttyACM0'}, '/dev/ttyACM0'), '')

    def test_native_alias_accepted(self):
        self.assertEqual(self.resolve({'/dev/atlas-sensor-hub':'/dev/ttyACM2',
            '/dev/serial/by-id/usb-Arduino_UNO_R4_WiFi_x-if00':'/dev/ttyACM2'},
            '/dev/atlas-sensor-hub'), '/dev/atlas-sensor-hub')

    def test_reenumerated_native_found(self):
        port = '/dev/serial/by-id/usb-Arduino_UNO_R4_WiFi_x-if00'
        self.assertEqual(self.resolve({port:'/dev/ttyACM3'}, '/missing'), port)

    def test_multiple_unknown_boards_not_selected(self):
        self.assertEqual(self.resolve({
            '/dev/serial/by-id/usb-Arduino_UNO_R4_WiFi_x-if00':'/dev/ttyACM2',
            '/dev/serial/by-id/usb-Arduino_UNO_R4_WiFi_y-if00':'/dev/ttyACM3'}, '/missing'), '')

    def test_web_refuses_stale_offline_or_future_feedback(self):
        tree = ast.parse(Path(__file__).with_name('atlas_status_web.py').read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                   and any(isinstance(f, ast.FunctionDef) and f.name == 'camera_move' for f in n.body))
        fn = method('atlas_status_web.py', cls.name, 'camera_move', {'time':time})
        for entry in ({}, {'ts':time.time()-20,'value':'online via=uno'},
                      {'ts':time.time(),'value':'offline: debug interface'},
                      {'ts':time.time()+20,'value':'online via=uno'}):
            obj = SimpleNamespace(lock=threading.Lock(),data={'camera_servo_status':entry})
            ok, message = fn(obj,'pan',1)
            self.assertFalse(ok)
            self.assertIn('no movement sent',message)


if __name__ == '__main__': unittest.main()
