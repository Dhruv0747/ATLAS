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
        self.assertEqual(st['stage2'], 'LOCKED')                # locked until stage 1 passes
        self.assertEqual(st['stage3'], 'LOCKED')
        self.assertTrue(e['gate'][1]['locked'] and e['gate'][1]['unlock_after'] == 1)
        self.assertFalse(e['gate'][0]['locked'])
        self.assertFalse(e['gate_open'])
        self.assertTrue(all(l['status'] == 'LOCKED' for l in e['later']))
        self.assertIn('do stage 1', e['next_step']['text'].lower())
        self.assertEqual(e['later'][0]['tool']['href'], '/v2/stage4')      # every step has a (locked) button slot
        self.assertEqual(e['later'][0]['unlock_after'], 'entry gate (stages 1-3)')
        self.assertEqual(e['later'][1]['unlock_after'], 'step 4')

    def test_stage1_needs_a_real_bounded_straight_pass(self):
        speed_file(self.d, 'speed_loop_check_1.json', verdict='FAIL')
        speed_file(self.d, 'speed_loop_check_2.json', end_reason='TIMEOUT')
        speed_file(self.d, 'speed_loop_check_3.json', icp_distance_m=0.1)
        self.assertEqual(self.ev()['gate'][0]['status'], 'NOT DONE')
        speed_file(self.d, 'speed_loop_check_4.json')
        g1 = self.ev()['gate'][0]
        self.assertEqual(g1['status'], 'PASS')
        self.assertIn('0.59', g1['evidence'])

    def test_stage2_unlocks_after_stage1_and_is_next(self):
        speed_file(self.d, 'speed_loop_check_4.json')
        e = self.ev()
        self.assertEqual(e['gate'][1]['status'], 'NOT DONE')
        self.assertFalse(e['gate'][1]['locked'])
        self.assertEqual(e['gate'][2]['status'], 'LOCKED')     # stage 3 waits for stage 2
        self.assertIn('do stage 2', e['next_step']['text'].lower())
        self.assertEqual(e['next_step']['href'], '/v2/stage2')

    def test_stage2_records_runs_and_pass_is_sticky(self):
        speed_file(self.d, 'speed_loop_check_4.json')
        fail = {'verdict': 'FAIL', 'checks': {'left_arc': True, 'right_arc': False}, 'detail': 'left +25 deg (YAW)',
                'failed': ['right_arc']}
        mp.record_stage2(fail, 'turn_check_1.json', progress_file=self.prog)
        g2 = self.ev()['gate'][1]
        self.assertEqual(g2['status'], 'IN PROGRESS')
        self.assertEqual(g2['history'][-1]['failed'], ['right_arc'])
        ok = {'verdict': 'PASS', 'checks': {'left_arc': True, 'right_arc': True, 'net_heading_within_15deg': True},
              'detail': 'left +25 deg (YAW) · right -25 deg (YAW) · net +0 deg'}
        mp.record_stage2(ok, 'turn_check_2.json', progress_file=self.prog)
        mp.record_stage2(fail, 'turn_check_3.json', progress_file=self.prog)     # a later FAIL keeps the PASS
        e = self.ev()
        self.assertEqual(e['gate'][1]['status'], 'PASS')
        self.assertIn('right -25', e['gate'][1]['evidence'])
        self.assertEqual(e['gate'][2]['status'], 'IN PROGRESS')                 # stage 3 now unlocked
        self.assertIn('do stage 3', e['next_step']['text'].lower())

    def test_passed_stage_stays_pass_even_if_earlier_is_open(self):
        speed_file(self.d, 'speed_loop_check_4.json')
        self.prog.write_text(json.dumps({'stage3_owner_decision': {'when': 'w', 'text': 't'}}))
        e = self.ev()
        self.assertEqual(e['gate'][2]['status'], 'PASS (OWNER DECISION)')
        self.assertEqual(e['next_step']['href'], '/v2/stage2')

    def test_stage3_pass_only_from_checker_pass_and_gate_opens(self):
        speed_file(self.d, 'speed_loop_check_4.json')
        mp.record_stage3({'verdict': 'FAIL', 'checks': {'legs': {'ok': True}, 'safe_stop': {'ok': False}}}, '/b1',
                         progress_file=self.prog)
        e = self.ev()
        self.assertEqual(e['gate'][2]['status'], 'LOCKED')     # stage 2 not passed yet; history is still kept
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
        self.assertEqual(e['later'][0]['status'], 'NOT DONE')                # only step 4 unlocks
        self.assertTrue(all(l['status'] == 'LOCKED' for l in e['later'][1:]))
        self.assertIn('step 4', e['next_step']['text'])
        self.assertEqual(e['next_step']['href'], '/v2/stage4')
        # step 4 part A PASS: shown as IN PROGRESS (part B is developer work); steps 5-10 stay locked
        mp.record_stage4a({'verdict': 'FAIL', 'failed': ['imu_rate'], 'detail': 'd1'}, 'imu_check_1.json',
                          progress_file=self.prog)
        self.assertEqual(self.ev()['later'][0]['status'], 'NOT DONE')
        mp.record_stage4a({'verdict': 'PASS', 'failed': [], 'detail': 'parked 60 s ok'}, 'imu_check_2.json',
                          progress_file=self.prog)
        e = self.ev()
        self.assertEqual(e['later'][0]['status'], 'IN PROGRESS')
        self.assertIn('Part B', e['later'][0]['evidence'])
        self.assertEqual(len(e['later'][0]['history']), 2)
        self.assertTrue(all(l['status'] == 'LOCKED' for l in e['later'][1:]))
        self.assertIsNone(e['next_step']['href'])
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
