"""Extend job (2026-11-26): turns an extend-session request into a preview, a report and (only if every check passes) a
candidate map. Never touches the saved map. Pure file IO; no ROS."""
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).parent))
import atlas_map_extend_core as ex  # noqa: E402
import atlas_map_extend_job as job  # noqa: E402
from atlas_map_acceptance_core import map_pair_id  # noqa: E402
from test_map_extend_core import T_TRUE, new_piece, old_map  # noqa: E402


class JobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.d = Path(self.tmp.name)
        (d / 'maps').mkdir()
        self.saved_yaml = ex.write_map(old_map(), d / 'maps' / 'atlas_latest')
        self.saved_bytes = (self.saved_yaml.read_bytes(), self.saved_yaml.with_suffix('.pgm').read_bytes())
        self.state = d / 'map_extend'
        self.session_file = d / 'mapping_session.json'

    def tearDown(self):
        self.tmp.cleanup()

    def request(self, sid='s1', init=T_TRUE, piece=None, base_id=None):
        cand = ex.write_map(piece or new_piece(T_TRUE), self.d / 'maps' / f'.atlas_candidate_{sid}')
        self.state.mkdir(exist_ok=True)
        base = base_id or map_pair_id(self.saved_yaml, self.saved_yaml.with_suffix('.pgm'))
        p = self.state / f'{sid}.request.json'
        p.write_text(json.dumps({'schema': 1, 'session_id': sid, 'state': 'pending', 'candidate_yaml': str(cand),
                                 'base_map_id': base, 'init': list(init), 'end_pose_slam': {'x': 1.0, 'y': 0.5}}))
        return p

    def run_job(self):
        return job.process_pending(self.state, self.saved_yaml, self.session_file)

    def saved_untouched(self):
        self.assertEqual((self.saved_yaml.read_bytes(), self.saved_yaml.with_suffix('.pgm').read_bytes()),
                         self.saved_bytes)

    def test_good_piece_gives_preview_and_candidate(self):
        req = self.request(init=(T_TRUE[0] + 0.2, T_TRUE[1] - 0.1, T_TRUE[2] + math.radians(3)))
        results = self.run_job()
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertTrue(r['ok'], r['failures'])
        out = self.state / 's1'
        self.assertTrue((out / 'preview.png').read_bytes().startswith(b'\x89PNG'))
        self.assertTrue((out / 'candidate.yaml').exists() and (out / 'candidate.pgm').exists())
        self.assertEqual(json.loads((self.state / 'latest.json').read_text())['session_id'], 's1')
        self.assertEqual(json.loads(req.read_text())['state'], 'done')
        self.assertEqual(r['stats']['saved_cells_changed'], 0)
        self.assertIn('end_pose_saved', r)
        self.assertEqual(self.run_job(), [])                       # done requests are not redone
        self.saved_untouched()

    def test_refused_when_saved_map_changed_since_the_session(self):
        self.request(base_id='an-older-map')
        r = self.run_job()[0]
        self.assertFalse(r['ok'])
        self.assertTrue(any('saved map changed' in f for f in r['failures']), r['failures'])
        self.assertFalse((self.state / 's1' / 'candidate.yaml').exists())
        self.saved_untouched()

    def test_waits_while_a_mapping_session_is_active(self):
        self.request()
        self.session_file.write_text('{"id": "x", "state": "active"}')
        self.assertEqual(self.run_job(), [])
        self.session_file.unlink()
        self.assertEqual(len(self.run_job()), 1)

    def test_bad_piece_no_candidate_but_preview_and_reasons(self):
        self.request(init=(T_TRUE[0] + 2.0, T_TRUE[1] - 1.5, T_TRUE[2] + math.radians(60)))
        r = self.run_job()[0]
        # a wrong start is retried with the wide search once; if even that fails the reasons are kept
        out = self.state / 's1'
        self.assertTrue((out / 'preview.png').exists())
        if not r['ok']:
            self.assertFalse((out / 'candidate.yaml').exists())
            self.assertTrue(r['failures'])
        else:
            self.assertTrue(r['used_wide_search'])
        self.saved_untouched()

    def test_missing_candidate_is_reported(self):
        req = self.request()
        Path(json.loads(req.read_text())['candidate_yaml']).unlink()
        r = self.run_job()[0]
        self.assertFalse(r['ok'])
        self.assertTrue(any('could not read' in f for f in r['failures']), r['failures'])

    def test_text_english(self):
        self.request(base_id='old')
        for f in self.run_job()[0]['failures']:
            self.assertFalse(any('ऀ' <= ch <= 'ॿ' for ch in f), f)


if __name__ == '__main__':
    unittest.main()
