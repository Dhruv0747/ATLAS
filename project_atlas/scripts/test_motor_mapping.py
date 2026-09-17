"""Pure mapping tests: does not import ROS or access hardware."""
import ast
from pathlib import Path
import unittest

tree = ast.parse(Path(__file__).with_name('yahboom_base.py').read_text())
function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'motor_outputs')
scope = {}
exec(compile(ast.Module(body=[function], type_ignores=[]), '<mapping>', 'exec'), scope)
outputs = scope['motor_outputs']

class MappingTests(unittest.TestCase):
    def test_stop(self):
        self.assertEqual(outputs(0, 0), (0, 0, 0, 0))
    def test_forward(self):
        self.assertEqual(outputs(50, 50), (-50, 50, -50, 50))
    def test_reverse(self):
        self.assertEqual(outputs(-50, -50), (50, -50, 50, -50))
    def test_left_right_assignment(self):
        self.assertEqual(outputs(30, 40), (-30, 40, -30, 40))

if __name__ == '__main__':
    unittest.main()
