"""One-click Stage-3 runner (2026-11-22): pure state machine, no ROS."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import atlas_stage3_runner as s3  # noqa: E402

START = (s3.START_X, s3.START_Y, s3.START_YAW_DEG)
HALL = (2.19, -5.58, -95.0)


def obs(pose=START, speed=0.0, latched=False, armed=True, mission='READY', source='STOPPED', std=0.05):
    return {'pose': pose, 'speed': speed, 'latched': latched, 'armed': armed, 'mission': mission,
            'source': source, 'xy_std': std}


class Sim:
    def __init__(self):
        self.r = s3.Runner(); self.t = 0.0; self.actions = []

    def run(self, seconds, **kw):
        end = self.t + seconds
        while self.t < end:
            self.actions += self.r.step(self.t, obs(**kw))
            self.t = round(self.t + 0.5, 1)

    def gos(self):
        return [a[1] for a in self.actions if a[0] == 'go']


class RunnerTests(unittest.TestCase):
    def test_at_start_records_then_goes_to_hall_after_still(self):
        s = Sim(); s.r.start(0.0)
        s.run(3)
        self.assertEqual(s.gos(), [])                      # not still long enough yet
        s.run(10)
        self.assertEqual(s.r.state, 'OUT')
        self.assertIn(('start_recording',), s.actions)
        self.assertEqual(s.gos(), ['hall'])
        self.assertLess(s.actions.index(('start_recording',)), s.actions.index(('go', 'hall')))

    def test_not_at_start_positions_first_without_recording(self):
        s = Sim(); s.r.start(0.0)
        s.run(8, pose=(1.0, -1.0, -60.0))
        self.assertEqual(s.gos(), ['dhruv room'])
        self.assertNotIn(('start_recording',), s.actions)
        s.run(2, pose=(1.0, -1.0, -60.0), mission='NAMED GOAL ACCEPTED name=dhruv room taught-route')
        s.run(1, mission='NAMED GOAL FINISHED name=dhruv room taught-route status=4')
        self.assertEqual(s.r.state, 'SETTLE')
        s.run(8, mission='NAMED GOAL FINISHED name=dhruv room taught-route status=4')
        self.assertEqual(s.gos(), ['dhruv room', 'hall'])
        self.assertIn(('start_recording',), s.actions)

    def test_never_sends_when_latched_or_autonomy_off(self):
        s = Sim(); s.r.start(0.0)
        s.run(20, latched=True)
        s.run(20, armed=False)
        self.assertEqual(s.gos(), [])
        self.assertIn('Autonomy is OFF', s.r.message)

    def test_full_round_trip_with_b_and_doorway_retry(self):
        s = Sim(); s.r.start(0.0)
        s.run(7)                                                       # -> OUT, go hall
        s.run(1, mission='NAMED GOAL ACCEPTED name=hall taught-route', source='NAV2', speed=0.12, pose=(0.5, 0.3, -60))
        s.run(2, mission='NAMED GOAL ACCEPTED name=hall taught-route', source='NAV2', speed=0.12, pose=(0.6, 0.2, -60))
        self.assertTrue(s.r.b_prompt)                                  # PRESS B NOW while rolling
        s.run(1, mission='NAMED GOAL ACCEPTED name=hall taught-route', source='STOPPED', speed=0.12, latched=True,
              pose=(0.6, 0.2, -60))
        self.assertTrue(s.r.stop_done)
        # goal failed in a doorway; owner helps, then ATLAS is still -> automatic resend
        s.run(1, mission='NAMED GOAL FINISHED name=hall taught-route status=6', pose=(1.3, -1.5, -70))
        s.run(4, mission='NAMED GOAL FINISHED name=hall taught-route status=6', pose=(1.6, -2.1, -70))
        self.assertEqual(s.gos(), ['hall'])                            # not yet: still timer + retry gap
        s.run(10, mission='NAMED GOAL FINISHED name=hall taught-route status=6', pose=(1.6, -2.1, -70))
        self.assertEqual(s.gos(), ['hall', 'hall'])
        s.run(1, mission='NAMED GOAL ACCEPTED name=hall taught-route', pose=(1.6, -2.1, -70))
        s.run(1, mission='NAMED GOAL FINISHED name=hall taught-route status=4', pose=HALL)
        self.assertEqual(s.r.state, 'HOME')
        s.run(8, mission='NAMED GOAL FINISHED name=hall taught-route status=4', pose=HALL)
        self.assertEqual(s.gos(), ['hall', 'hall', 'dhruv room'])
        s.run(1, mission='NAMED GOAL ACCEPTED name=dhruv room taught-route', pose=HALL)
        s.run(1, mission='NAMED GOAL FINISHED name=dhruv room taught-route status=4')
        self.assertEqual(s.r.state, 'CHECK')
        self.assertIn(('stop_recording', 'done'), s.actions)
        self.assertIn(('run_checker',), s.actions)
        s.r.finish_check(s.t, {'verdict': 'PASS'})
        self.assertEqual(s.r.state, 'DONE')
        self.assertIn('PASS', s.r.message)

    def test_b_press_while_still_does_not_count(self):
        s = Sim(); s.r.start(0.0)
        s.run(7)
        s.run(1, mission='NAMED GOAL ACCEPTED name=hall taught-route', source='NAV2', speed=0.0)
        s.run(1, mission='NAMED GOAL ACCEPTED name=hall taught-route', latched=True, speed=0.0)
        self.assertFalse(s.r.stop_done)

    def test_cancel_stops_recording_and_sends_nothing_more(self):
        s = Sim(); s.r.start(0.0)
        s.run(7)
        acts = s.r.cancel(s.t)
        self.assertEqual(acts, [('stop_recording', 'cancelled')])
        n = len(s.gos())
        s.run(30)
        self.assertEqual(len(s.gos()), n)
        self.assertEqual(s.r.state, 'CANCELLED')

    def test_mission_error_waits_and_retries(self):
        s = Sim(); s.r.start(0.0)
        s.run(7)
        s.run(1, mission='ERROR navigate named place hall: saved-map navigation blocked: current pose is not in known clear space')
        self.assertIsNone(s.r.leg)
        s.run(10, mission='ERROR navigate named place hall: saved-map navigation blocked: current pose is not in known clear space')
        self.assertEqual(s.gos(), ['hall', 'hall'])

    def test_start_twice_refused_while_running(self):
        r = s3.Runner()
        self.assertTrue(r.start(0.0)[0])
        self.assertFalse(r.start(1.0)[0])


if __name__ == '__main__':
    unittest.main()


class FakeRecorder:
    def __init__(self): self.calls = []; self.on = False
    def start(self): self.calls.append('start'); self.on = True; return '/tmp/bag_x'
    def stop(self): self.calls.append('stop'); self.on = False
    def running(self): return self.on


class ServiceTests(unittest.TestCase):
    def make(self, go_ok=True):
        self.clock = [0.0]; self.sent = []; self.cur = obs()
        rec = FakeRecorder()
        svc = s3.Service(lambda: dict(self.cur), lambda p: (self.sent.append(p) or (go_ok, 'refused by test')),
                         recorder=rec, checker=lambda bag: {'verdict': 'PASS', 'checks': {}, 'raw': bag},
                         clock=lambda: self.clock[0])
        svc.runner.start(0.0)
        return svc, rec

    def tick(self, svc, seconds):
        end = self.clock[0] + seconds
        while self.clock[0] < end:
            svc.tick(); self.clock[0] = round(self.clock[0] + 0.5, 1)

    def test_records_sends_and_checks(self):
        svc, rec = self.make()
        self.tick(svc, 7)
        self.assertEqual(rec.calls, ['start']); self.assertEqual(self.sent, ['hall'])
        self.cur = obs(mission='NAMED GOAL FINISHED name=hall taught-route status=4', pose=HALL); self.tick(svc, 9)
        self.assertEqual(self.sent, ['hall', 'dhruv room'])
        self.cur = obs(mission='NAMED GOAL FINISHED name=dhruv room taught-route status=4'); self.tick(svc, 1)
        self.assertEqual(rec.calls, ['start', 'stop'])
        snap = svc.snapshot()
        self.assertEqual(snap['state'], 'DONE'); self.assertEqual(snap['result']['verdict'], 'PASS')
        self.assertEqual(snap['bag'], '/tmp/bag_x')

    def test_refused_go_is_retried_later_not_lost(self):
        svc, rec = self.make(go_ok=False)
        self.tick(svc, 7)
        self.assertEqual(self.sent, ['hall'])
        self.assertIsNone(svc.runner.leg)
        self.assertIn('not sent', svc.runner.message)

    def test_bad_status_read_sends_nothing(self):
        svc, rec = self.make()
        def boom(): raise RuntimeError('ros down')
        svc.obs_fn = boom
        self.tick(svc, 20)
        self.assertEqual(self.sent, [])

    def test_checker_output_parsing(self):
        out = ('PASS  legs         finished: hall=4, dhruv room=4\nFAIL  return_home  0.23 m / 31 deg from the start pose\n'
               'PASS  safe_stop    1/1 stops within 1.5 s\nSTAGE 3: FAIL\n')
        class P: stdout = out
        res = s3.run_checker('/tmp/b', runner=lambda *a, **k: P())
        self.assertEqual(res['verdict'], 'FAIL')
        self.assertFalse(res['checks']['return_home']['ok'])
        self.assertTrue(res['checks']['safe_stop']['ok'])
