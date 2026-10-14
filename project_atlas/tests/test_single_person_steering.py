"""Stage 17B fake-clock integration with the actual steering-owner lease core."""
import math
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from atlas_single_person_steering import PLAN, SinglePersonSteering, caliper_angle, measurement_report
from atlas_steering_commission import SteeringCommission

DEFAULTS = {'front': {'center': 90, 'left': 121, 'right': 50},
            'rear': {'center': 90, 'left': 134, 'right': 59}}
CLIENT = 'a'*32
CONFIRM = dict(lifted=True, charger_disconnected=True, hands_clear=True, cutoff_ready=True)


class Rig:
    def __init__(self, root, mode='observe', enabled=True):
        self.now = 0.0
        self.applied = {'front': 90, 'rear': 90}
        self.owner = SteeringCommission(Path(root)/'steering.json', DEFAULTS)
        self.requests, self.stops, self.spoken = [], [], []
        self.safe = self.recording = True
        self.engine = SinglePersonSteering(self.send, self.stop, announce=self.spoken.append, enabled=enabled)
        self.mode = mode

    def send(self, message):
        self.requests.append(dict(message))
        self.owner.command(message, self.now, self.applied, self.safe)

    def stop(self, reason):
        self.stops.append(reason)
        self.owner.freeze(self.applied, reason)

    def snapshot(self):
        owner = self.owner.status()
        owner['traction_inhibited'] = self.owner.locked
        return dict(safe=self.safe, owner=owner, recorder_ready=self.recording,
                    front_applied=self.applied['front'], rear_applied=self.applied['rear'])

    def advance(self, seconds):
        for _ in range(round(seconds/.1)):
            self.now = round(self.now+.1, 6)
            self.owner.tick(self.now, self.applied, self.safe)
            for side in self.applied:
                target = self.owner.targets[side]
                self.applied[side] += max(-1, min(1, target-self.applied[side]))
            self.engine.tick(self.now, self.snapshot())

    def ready(self):
        self.engine.prepare(CLIENT, self.now, self.snapshot(), CONFIRM, self.mode)
        self.advance(.3)
        assert self.engine.state == 'READY'

    def start(self):
        self.ready()
        self.engine.start(CLIENT, self.now, self.snapshot(), True, True)


class SinglePersonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.rig = Rig(self.temp.name)
    def tearDown(self): self.temp.cleanup()

    def test_disabled_prepare_has_no_side_effects(self):
        rig = Rig(self.temp.name, enabled=False)
        with self.assertRaises(ValueError):
            rig.ready()
        self.assertEqual(rig.requests, [])

    def test_no_motion_before_explicit_start_and_centre_permission(self):
        self.rig.ready(); self.rig.advance(5)
        self.assertFalse(any(r['op'] == 'jog' for r in self.rig.requests))
        with self.assertRaises(ValueError):
            self.rig.engine.start(CLIENT, self.rig.now, self.rig.snapshot(), True, False)
        self.assertEqual(self.rig.applied, {'front': 90, 'rear': 90})

    def test_full_sequence_order_hold_and_phone_background(self):
        self.rig.start(); self.rig.advance(195)
        engine = self.rig.engine
        self.assertEqual(engine.state, 'COMPLETE')
        commands = [e for e in engine.events if e['event'] == 'command']
        self.assertEqual([e['command_pwm_deg'] for e in commands], list(PLAN))
        for hold in (e for e in engine.events if e['event'] == 'hold_15_seconds'):
            transitions = [e for e in engine.events if e['event'] in ('next_countdown', 'complete')
                           and e['monotonic_s'] > hold['monotonic_s']]
            self.assertGreaterEqual(transitions[0]['monotonic_s']-hold['monotonic_s'], 15-1e-7)
        self.assertFalse(any(r.get('side') == 'rear' for r in self.rig.requests))
        self.assertTrue(all(r['op'] in ('enter', 'heartbeat', 'jog') for r in self.rig.requests))
        self.assertFalse((Path(self.temp.name)/'steering.json').exists())
        self.assertEqual(self.rig.owner.saved, DEFAULTS)
        self.assertEqual(self.rig.applied['rear'], 90)

    def test_estop_safety_precedes_due_step(self):
        self.rig.start(); self.rig.advance(35)
        count = len([r for r in self.rig.requests if r['op'] == 'jog'])
        self.rig.safe = False; self.rig.advance(.1)
        self.assertEqual(self.rig.engine.state, 'CANCELLED')
        self.rig.advance(40)
        self.assertEqual(count, len([r for r in self.rig.requests if r['op'] == 'jog']))
        self.assertTrue(self.rig.owner.locked)

    def test_remote_b_owner_freeze_cancels_without_recentering(self):
        self.rig.start(); self.rig.advance(35)
        current = dict(self.rig.applied)
        self.rig.owner.freeze(current, 'Remote B stop'); self.rig.advance(.1)
        self.assertEqual(self.rig.engine.state, 'CANCELLED')
        self.assertEqual(self.rig.owner.targets, current)

    def test_owner_connection_interruption(self):
        self.rig.start(); self.rig.advance(35)
        snap = self.rig.snapshot(); snap['safe'] = False; snap['problem'] = 'owner status stale'
        self.rig.engine.tick(self.rig.now+.1, snap)
        self.assertEqual(self.rig.engine.reason, 'owner status stale')
        self.assertEqual(self.rig.owner.targets, self.rig.applied)

    def test_supervisor_delay_and_lease_expiry(self):
        self.rig.start(); self.rig.advance(35)
        self.rig.now += 2
        self.rig.owner.tick(self.rig.now, self.rig.applied, True)
        self.rig.engine.tick(self.rig.now, self.rig.snapshot())
        self.assertEqual(self.rig.engine.state, 'CANCELLED')
        self.assertFalse(self.rig.owner.status()['lease_active'])

    def test_caliper_pauses_and_requires_hands_clear(self):
        self.rig.mode = 'caliper'; self.rig.start(); self.rig.advance(27)
        self.assertEqual(self.rig.engine.state, 'PAUSED')
        before = len(self.rig.requests)
        self.rig.advance(10)
        self.assertFalse(any(r['op'] == 'jog' for r in self.rig.requests[before:]))
        with self.assertRaises(ValueError):
            self.rig.engine.resume(CLIENT, self.rig.now, False)
        self.rig.engine.resume(CLIENT, self.rig.now, True)
        self.rig.advance(6)
        self.assertEqual(self.rig.applied['front'], 95)

    def test_maximum_duration_does_not_extend_for_pause(self):
        self.rig.mode = 'caliper'; self.rig.start(); deadline = self.rig.engine.deadline
        self.rig.advance(301)
        self.assertEqual(self.rig.engine.state, 'CANCELLED')
        self.assertEqual(self.rig.engine.deadline, deadline)

    def test_emergency_cancels_and_service_restart_does_not_resume(self):
        self.rig.start(); self.rig.advance(35)
        self.rig.engine.emergency(self.rig.now)
        new = SinglePersonSteering(self.rig.send, self.rig.stop, enabled=True)
        requests = len(self.rig.requests); new.tick(self.rig.now+.1, self.rig.snapshot())
        self.assertEqual(new.state, 'IDLE')
        self.assertEqual(len(self.rig.requests), requests)

    def test_recorder_failure_cancels_sequence(self):
        self.rig.start(); self.rig.advance(35); self.rig.recording = False
        self.rig.advance(.1)
        self.assertEqual(self.rig.engine.state, 'CANCELLED')
        self.assertIn('recorder', self.rig.engine.reason)

    def test_rear_or_non90_saved_centre_blocks_prepare(self):
        self.rig.applied['rear'] = 91
        with self.assertRaises(ValueError): self.rig.ready()
        self.assertEqual(self.rig.requests, [])

    def test_phone_tilt_is_not_accepted_as_measurement(self):
        with self.assertRaises(ValueError):
            measurement_report([{'front_left': 90}]*9, 'phone_tilt')

    def test_caliper_geometry_and_hysteresis(self):
        angle, bound = caliper_angle(80*math.sin(math.radians(10)), 80, 1)
        self.assertAlmostEqual(angle, 10)
        self.assertGreater(bound, 1)
        values = [0, 5, 10, 6, 1, -5, -10, -4, 0]
        report = measurement_report([{'front_left': v} for v in values], 'visual_protractor', 2)
        self.assertEqual(report['wheels']['front_left']['return_minus_outward_deg']['95'], 1)
        self.assertEqual(report['wheels']['front_left']['deflection_bound_deg'][1], 4)
        self.assertFalse(report['calibration_written'])
        self.assertFalse(report['wheels']['front_right']['valid'])


if __name__ == '__main__': unittest.main()
