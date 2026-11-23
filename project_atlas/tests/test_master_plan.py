"""Master-plan progress board (2026-11-23): status only from recorded evidence."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import atlas_master_plan as mp  # noqa: E402


def speed_file(d, name, **kw):
    r = dict(verdict='PASS', end_reason='DISTANCE', wheel_distance_m=0.595, icp_distance_m=0.667, coast_after_stop_m=0.02)
    r.update(kw)
    (Path(d) / name).write_text(json.dumps(r))


class MasterPlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.d = Path(self.tmp.name); self.prog = self.d / 'p.json'

    def tearDown(self):
        self.tmp.cleanup()

    def ev(self):
        return mp.evaluate(state_dir=self.d, progress_file=self.prog)

    def test_nothing_recorded(self):
        e = self.ev()
        st = {g['id']: g['status'] for g in e['gate']}
        self.assertEqual(st['stage1'], 'NOT DONE')
        self.assertEqual(st['stage2'], 'NOT DONE')
        self.assertEqual(st['stage3'], 'IN PROGRESS')          # history of runs 7-9 is kept
        self.assertFalse(e['gate_open'])
        self.assertTrue(all(l['status'] == 'LOCKED' for l in e['later']))
        self.assertIn('do stage 1', e['next_step']['text'].lower())

    def test_stage1_needs_a_real_bounded_straight_pass(self):
        speed_file(self.d, 'speed_loop_check_1.json', verdict='FAIL')
        speed_file(self.d, 'speed_loop_check_2.json', end_reason='TIMEOUT')
        speed_file(self.d, 'speed_loop_check_3.json', icp_distance_m=0.1)
        self.assertEqual(self.ev()['gate'][0]['status'], 'NOT DONE')
        speed_file(self.d, 'speed_loop_check_4.json')
        g1 = self.ev()['gate'][0]
        self.assertEqual(g1['status'], 'PASS')
        self.assertIn('0.59', g1['evidence'])

    def test_next_step_prefers_a_stage_the_owner_can_do_now(self):
        speed_file(self.d, 'speed_loop_check_4.json')
        e = self.ev()
        self.assertIn('do stage 3', e['next_step']['text'].lower())          # stage 3 has the one-click tool
        self.assertEqual(e['next_step']['href'], '/v2/stage3')
        self.assertIn('stage 2', e['next_step']['text'].lower())             # and says stage 2 needs a tool

    def test_only_stage2_left_says_it_needs_a_tool(self):
        speed_file(self.d, 'speed_loop_check_4.json')
        mp.record_stage3({'verdict': 'PASS', 'checks': {'legs': {'ok': True}}}, '/b', progress_file=self.prog)
        e = self.ev()
        self.assertIn('needs a test tool', e['next_step']['text'])
        self.assertIsNone(e['next_step']['href'])

    def test_stage3_pass_only_from_checker_pass_and_gate_opens(self):
        speed_file(self.d, 'speed_loop_check_4.json')
        mp.record_stage3({'verdict': 'FAIL', 'checks': {'legs': {'ok': True}, 'safe_stop': {'ok': False}}}, '/b1',
                         progress_file=self.prog)
        e = self.ev()
        self.assertEqual(e['gate'][2]['status'], 'IN PROGRESS')
        self.assertEqual(e['gate'][2]['history'][-1]['failed'], ['safe_stop'])
        mp.record_stage3({'verdict': 'PASS', 'checks': {k: {'ok': True} for k in ('legs', 'return_home', 'safe_stop',
                                                                                    'turn_sign', 'encoders')}},
                         '/b2', progress_file=self.prog)
        self.prog_data = json.loads(self.prog.read_text())
        self.assertEqual(self.prog_data['stage3_runs'][-1]['score'], '5/5')
        e = self.ev()
        self.assertEqual(e['gate'][2]['status'], 'PASS')
        self.assertFalse(e['gate_open'])                        # stage 2 still open
        (self.prog).write_text(json.dumps(dict(self.prog_data, stage2={'verdict': 'PASS', 'detail': 'turns ok'})))
        e = self.ev()
        self.assertTrue(e['gate_open'])
        self.assertTrue(all(l['status'] == 'NEEDS DEVELOPER' for l in e['later']))
        self.assertEqual(e['gate_done'], 3)

    def test_owner_decision_is_shown_as_such(self):
        speed_file(self.d, 'speed_loop_check_4.json')
        self.prog.write_text(json.dumps({'stage3_owner_decision': {'when': '2026-11-23 13:00',
                                                                   'text': 'return_home from run A, safe stop from run B'}}))
        g3 = self.ev()['gate'][2]
        self.assertEqual(g3['status'], 'PASS (OWNER DECISION)')
        self.assertIn('OWNER DECISION', g3['evidence']); self.assertIn('run B', g3['evidence'])
        self.assertEqual(self.ev()['gate_done'], 2)
        self.prog.write_text(json.dumps({'stage3_owner_decision': {'when': 'x'}}))       # no text -> ignored
        self.assertNotEqual(self.ev()['gate'][2]['status'], 'PASS (OWNER DECISION)')

    def test_history_is_bounded(self):
        for i in range(40):
            mp.record_stage3({'verdict': 'FAIL', 'checks': {}}, '/b%d' % i, progress_file=self.prog)
        self.assertEqual(len(json.loads(self.prog.read_text())['stage3_runs']), 30)


if __name__ == '__main__':
    unittest.main()
