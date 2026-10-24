import unittest
from summarize_python_profile import summarize


class AttributionTest(unittest.TestCase):
    def test_recursive_frame_counted_once_inclusive(self):
        data = {'shared': {'frames': [{'name': 'a', 'file': 'a.py', 'line': 1},
                                      {'name': 'b', 'file': 'b.py', 'line': 2}]},
                'profiles': [{'type': 'sampled', 'name': 'thread',
                              'samples': [[0, 0, 1], [0], []]}]}
        result = summarize(data)
        self.assertEqual(result['samples'], 3)
        self.assertEqual(dict(result['inclusive'])['a.py:1 a'], 2)
        self.assertEqual(dict(result['leaf'])['b.py:2 b'], 1)

    def test_reject_event_profile(self):
        with self.assertRaises(ValueError):
            summarize({'shared': {'frames': []}, 'profiles': [{'type': 'evented'}]})


if __name__ == '__main__': unittest.main()
