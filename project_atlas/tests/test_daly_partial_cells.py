"""Exercise production decoder without ROS or Bluetooth."""
import ast
from pathlib import Path
import re
import unittest

source = Path(__file__).parents[1] / 'scripts' / 'daly_bms_node.py'
tree = ast.parse(source.read_text(encoding='utf-8'))
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'DalyBmsNode')
methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in ('decode', 'split_frames', 'u16')]
namespace = {'re': re}
exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), 'exec'), namespace)
Decoder = type('Decoder', (), {**{n.name: namespace[n.name] for n in methods}, 'correct_soc': lambda self, data: None})


def page(number, values):
    payload = [number]
    for v in values:
        payload.extend([v >> 8, v & 255])
    frame = [0xA5, 1, 0x95, 8] + payload + [0, 0]
    return 'Notification handle = 1 value: ' + ' '.join(f'{v:02x}' for v in frame)


class PartialCells(unittest.TestCase):
    def test_partial_does_not_invent_zero_cells(self):
        result = Decoder().decode(page(2, [3250, 0, 0]))
        self.assertFalse(result['cells_complete'])
        self.assertEqual(result['missing_cell_indices'], [1, 2, 3])
        self.assertNotIn('cells_v', result)

    def test_complete_poll(self):
        result = Decoder().decode(page(1, [3240, 3250, 3260])+'\n'+page(2, [3270, 0, 0]))
        self.assertTrue(result['cells_complete'])
        self.assertEqual(result['cells_v'], [3.24, 3.25, 3.26, 3.27])

    def test_no_cross_poll_fill(self):
        decoder = Decoder()
        decoder.decode(page(1, [3240, 3250, 3260]))
        self.assertFalse(decoder.decode(page(2, [3270, 0, 0]))['cells_complete'])


if __name__ == '__main__':
    unittest.main()
