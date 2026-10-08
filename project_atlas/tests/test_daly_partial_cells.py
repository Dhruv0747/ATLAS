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
    frame[-1] = sum(frame[:-1]) & 255
    return 'Notification handle = 1 value: ' + ' '.join(f'{v:02x}' for v in frame)


class PartialCells(unittest.TestCase):
    def test_payload_a5_is_not_a_new_frame(self):
        result = Decoder().decode(page(1, [3237, 3250, 3260])+'\n'+page(2, [3270, 0, 0]))
        self.assertTrue(result['cells_complete'])
        self.assertEqual(result['cells_v'][0], 3.237)

    def test_truncated_second_frame_is_not_complete(self):
        text = page(1, [3240, 3250, 3260]) + '\n' + page(2, [3270, 0, 0])
        result = Decoder().decode(text.rsplit(' ', 6)[0])
        self.assertFalse(result['cells_complete'])
        self.assertEqual(result['missing_cell_indices'], [4])

    def test_notification_fragment_reassembly(self):
        text = page(1, [3240, 3250, 3260])
        prefix, data = text.split('value: ')
        words = data.split()
        result = Decoder().decode(prefix+'value: '+' '.join(words[:8])+'\n'+prefix+'value: '+' '.join(words[8:]))
        self.assertEqual(result['missing_cell_indices'], [4])

    def test_bad_checksum_discarded(self):
        text = page(1, [3240, 3250, 3260])
        self.assertEqual(Decoder().decode(text[:-2]+'ff'), {})

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
