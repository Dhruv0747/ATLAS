from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import atlas_autonomy_arm
from atlas_autonomy_arm import AutonomyArm, read_gate

NO_EVIDENCE = {'ok': False, 'enabled': False, 'passed': [], 'missing': [0.15], 'latest': {}}

READY = {'autonomy_ready': True}


def gate(text):
    f = tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False)
    f.write(text); f.close()
    return f.name


class AutonomyArmTests(unittest.TestCase):
    def setUp(self):
        # hermetic: never read the real ~/.local/state speed-check evidence (on the rover it holds live PASSes)
        patcher = mock.patch.object(atlas_autonomy_arm, 'speed_evidence', return_value=dict(NO_EVIDENCE))
        patcher.start(); self.addCleanup(patcher.stop)
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


class SpeedEvidenceTests(unittest.TestCase):
    def setUp(self):
        import json, os, time
        self.json, self.os, self.time = json, os, time
        self.dir = Path(tempfile.mkdtemp())
        self.cfg = self.dir / 'speed_loop.yaml'
        self.cfg.write_text('speed_loop:\n  enabled: true\n')
        self.code = self.dir / 'atlas_speed_loop.py'
        self.code.write_text('# code\n')
        old = self.time.time() - 100
        os.utime(self.cfg, (old, old)); os.utime(self.code, (old, old))

    def result(self, name, target, verdict, age_s=10):
        f = self.dir / f'speed_loop_check_{name}.json'
        f.write_text(self.json.dumps({'target_mps': target, 'verdict': verdict, 'checks': {'a': verdict == 'PASS'}}))
        t = self.time.time() - age_s
        self.os.utime(f, (t, t))

    def ev(self):
        from atlas_autonomy_arm import speed_evidence
        return speed_evidence(self.dir, self.cfg, (self.code,))

    def test_needs_two_passes_at_015(self):
        self.result('1', 0.15, 'PASS')
        e = self.ev(); self.assertFalse(e['ok']); self.assertEqual(e['missing'], [0.15])
        self.result('2', 0.10, 'PASS')                           # other speeds do not count
        self.assertFalse(self.ev()['ok'])
        self.result('3', 0.15, 'PASS')
        self.assertTrue(self.ev()['ok'])

    def test_requested_speed_key_preferred(self):
        import json as j
        for n in ('a', 'b'):
            f = self.dir / f'speed_loop_check_{n}.json'
            f.write_text(j.dumps({'target_mps': 0.075, 'requested_mps': 0.15, 'verdict': 'PASS', 'checks': {}}))
        self.assertTrue(self.ev()['ok'])

    def test_fail_does_not_count(self):
        self.result('1', 0.15, 'PASS'); self.result('2', 0.15, 'FAIL')
        e = self.ev(); self.assertFalse(e['ok']); self.assertEqual(e['latest'][0.15]['failed_checks'], ['a'])

    def test_older_than_config_change_is_stale(self):
        self.result('1', 0.15, 'PASS', age_s=500); self.result('2', 0.15, 'PASS', age_s=500)
        self.assertFalse(self.ev()['ok'])

    def test_disabled_loop_never_ok(self):
        self.result('1', 0.15, 'PASS'); self.result('2', 0.15, 'PASS')
        self.cfg.write_text('speed_loop:\n  enabled: false\n')
        old = self.time.time() - 100; self.os.utime(self.cfg, (old, old))
        self.assertFalse(self.ev()['ok'])

    def test_gate_uses_evidence(self):
        no = gate('speed_validated: false\n')
        self.assertTrue(read_gate(no, evidence={'ok': True, 'enabled': True, 'missing': []})['speed_validated'])
        g = read_gate(no, evidence={'ok': False, 'enabled': True, 'missing': [0.15], 'passed': [0.15]})
        self.assertFalse(g['speed_validated']); self.assertIn('0.15', g['note']); self.assertIn('1/2', g['note'])
        a = AutonomyArm(True, no, evidence_override={'ok': True, 'enabled': True, 'missing': []})
        self.assertTrue(a.arm(True, False, READY, 0.1)[0])


if __name__ == '__main__':
    unittest.main()
