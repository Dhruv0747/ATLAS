"""Pure mapping tests, no ROS publishers or hardware commands."""
import ast
import math
from pathlib import Path
import unittest

tree = ast.parse(Path(__file__).with_name('camera_joystick_node.py').read_text())
scope = {'math': math}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef)
    and n.name in ('camera_input', 'camera_step', 'bounded_step')], type_ignores=[]), '<mapping>', 'exec'), scope)
read = scope['camera_input']
step = scope['camera_step']

class CameraTests(unittest.TestCase):
    def test_no_large_jump_after_packet_gap(self):
        bounded = scope['bounded_step']
        self.assertEqual(bounded(10, 0, 400), 16)
        self.assertEqual(bounded(10, 1, 400), 24)
        self.assertLessEqual(bounded(1.05, 1, 400), 20)
    def test_b_overrides_all_camera_inputs(self):
        self.assertEqual(read([0]*6+[1,1], [0,1,0,1]), (0,0,False))
    def test_drive_controls_do_not_move_camera(self):
        self.assertEqual(read([1,1,1,1,1,1,0,0], [0,0,0,0,1,1]), (0,0,False))
    def test_directions(self):
        self.assertEqual(step(1500,1500,1,1,50,50),(1450,1550))
        self.assertEqual(step(1500,1500,-1,-1,50,50),(1550,1450))
    def test_limits(self):
        self.assertEqual(step(700,2300,1,1,50,50),(700,2300))
        self.assertEqual(step(2300,700,-1,-1,50,50),(2300,700))
    def test_y_home_and_invalid(self):
        self.assertTrue(read([0]*8,[0,0,0,1])[2])
        self.assertEqual(read([],[]),(0,0,False))
        self.assertEqual(read([math.nan]*8,[0]*4),(0,0,False))

if __name__ == '__main__':
    unittest.main()
