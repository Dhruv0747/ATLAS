from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from atlas_autonomy_arm import AutonomyArm, read_gate

READY = {'autonomy_ready': True}


def gate(text):
    f = tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False)
    f.write(text); f.close()
    return f.name


class AutonomyArmTests(unittest.TestCase):
    def setUp(self):
        self.ok = gate('speed_validated: true\n')
        self.no = gate('speed_validated: false\nnote: speed calibration pending\n')

    def test_boot_is_off_and_manual_only_holds(self):
        a = AutonomyArm(True, self.ok)
        self.assertFalse(a.armed)
        self.assertTrue(a.manual_only(True))

    def test_arm_requires_latched_still_encoder_and_speed_gate(self):
        a = AutonomyArm(True, self.ok)
        self.assertFalse(a.arm(False, False, READY, 0.1)[0])          # not latched
        self.assertFalse(a.arm(True, True, READY, 0.1)[0])            # moving
        self.assertFalse(a.arm(True, False, {'autonomy_ready': False}, 0.1)[0])
        self.assertFalse(a.arm(True, False, READY, 5.0)[0])           # stale encoder
        self.assertFalse(a.arm(True, False, READY, None)[0])
        ok, msg = a.arm(True, False, READY, 0.1)
        self.assertTrue(ok, msg)
        self.assertFalse(a.manual_only(True))

    def test_speed_gate_blocks(self):
        a = AutonomyArm(True, self.no)
        ok, msg = a.arm(True, False, READY, 0.1)
        self.assertFalse(ok)
        self.assertIn('speed', msg)

    def test_missing_or_garbage_gate_blocks(self):
        self.assertFalse(read_gate('/nonexistent/gate.yaml')['speed_validated'])
        self.assertFalse(read_gate(gate('speed_validated: yes please\n'))['speed_validated'])
        self.assertFalse(AutonomyArm(True, '/nonexistent').arm(True, False, READY, 0.1)[0])

    def test_runtime_switch_disabled_keeps_hard_lock(self):
        a = AutonomyArm(False, self.ok)
        self.assertFalse(a.arm(True, False, READY, 0.1)[0])
        a.armed = True                     # even if forced, env lock wins without the runtime switch
        self.assertTrue(a.manual_only(True))

    def test_env_not_manual_only_is_unchanged(self):
        self.assertFalse(AutonomyArm(True, self.no).manual_only(False))

    def test_new_latch_edge_disarms_but_arming_while_latched_does_not(self):
        a = AutonomyArm(True, self.ok)
        a.observe_latch(True)
        self.assertTrue(a.arm(True, False, READY, 0.1)[0])
        self.assertFalse(a.observe_latch(True))     # still the same latch
        self.assertTrue(a.armed)
        a.observe_latch(False)                      # operator releases
        self.assertTrue(a.armed)
        self.assertTrue(a.observe_latch(True))      # any new E-STOP
        self.assertFalse(a.armed)
        self.assertTrue(a.manual_only(True))

    def test_disarm_always_works(self):
        a = AutonomyArm(True, self.ok)
        a.arm(True, False, READY, 0.1)
        self.assertTrue(a.disarm())
        self.assertFalse(a.disarm())
        self.assertFalse(a.armed)

    def test_status_lists_blockers_only_when_off(self):
        a = AutonomyArm(True, self.no)
        s = a.status(True, False, READY, 0.1)
        self.assertFalse(s['armed']); self.assertTrue(s['arm_blockers'])


if __name__ == '__main__':
    unittest.main()
