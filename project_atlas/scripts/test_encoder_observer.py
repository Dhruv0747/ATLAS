"""Pure framing tests: no ROS graph and no serial device access."""
import ast
from pathlib import Path
import struct
import unittest

tree = ast.parse(Path(__file__).with_name('atlas_encoder_observer.py').read_text())
function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'extract_frames')
namespace = {}
exec(compile(ast.Module(body=[function], type_ignores=[]), '<parser>', 'exec'), namespace)
parse = namespace['extract_frames']

def packet(values):
    body = bytes([19, 13]) + struct.pack('<4i', *values)
    return b'\xff\xfb' + body + bytes([sum(body) % 256])

class ParserTest(unittest.TestCase):
    def test_signed_counts(self):
        self.assertEqual(parse(bytearray(packet([1, -2, 300, -400]))), [(13, struct.pack('<4i', 1, -2, 300, -400))])
    def test_partial(self):
        p = packet([0]*4)
        b = bytearray(p[:8])
        self.assertEqual(parse(b), [])
        b.extend(p[8:])
        self.assertEqual(len(parse(b)), 1)
    def test_noise_and_checksum(self):
        p = packet([0]*4)
        b = bytearray(b'noise' + p[:-1] + bytes([p[-1] ^ 1]) + p)
        self.assertEqual(len(parse(b)), 1)
    def test_no_transmit(self):
        for name in ('atlas_encoder_observer.py', 'atlas_im10a_observer.py'):
            tree = ast.parse(Path(__file__).with_name(name).read_text())
            self.assertFalse(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                                and n.func.attr == 'write' for n in ast.walk(tree)))

if __name__ == '__main__':
    unittest.main()
