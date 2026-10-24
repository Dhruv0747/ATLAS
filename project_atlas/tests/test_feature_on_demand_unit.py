"""Unit tests for scripts/atlas_feature_on_demand.py decision logic (no ROS)."""
import importlib.util, json, os, tempfile, unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fod', ROOT / 'scripts/atlas_feature_on_demand.py')
F = importlib.util.module_from_spec(spec); spec.loader.exec_module(F)


class Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


PARKED = json.dumps({'manual_only': True, 'stop_latched': True})


class DemandLogic(unittest.TestCase):
    def setUp(self):
        self.c = Clock(); self.d = F.Demand(dict(F.DEFAULTS), clock=self.c)

    def test_fail_open_when_policy_or_mission_unknown_or_stale(self):
        self.assertTrue(self.d.active()['autonomy'])                        # nothing received yet
        self.d.on_policy(PARKED); self.assertTrue(self.d.active()['autonomy'])   # mission still unknown
        self.d.on_mission('READY'); self.assertFalse(self.d.active()['autonomy'])
        self.c.t += 6; self.assertTrue(self.d.active()['autonomy'])          # policy stale (> 5 s)
        self.d.on_policy('not json'); self.d.on_mission('READY'); self.assertTrue(self.d.active()['autonomy'])

    def test_autonomy_when_manual_only_off_or_mission_running(self):
        self.d.on_policy(json.dumps({'manual_only': False})); self.d.on_mission('READY'); self.assertTrue(self.d.active()['autonomy'])
        self.d.on_policy(PARKED); self.d.on_mission('NAVIGATING TO KITCHEN'); self.assertTrue(self.d.active()['autonomy'])

    def test_feature_triggers_and_windows(self):
        self.d.on_ai(True); self.assertTrue(self.d.active()['ai_object']); self.c.t += 61; self.assertFalse(self.d.active()['ai_object'])
        self.d.on_follow(True); self.assertTrue(self.d.active()['follow']); self.d.on_follow(False); self.assertFalse(self.d.active()['follow'])
        self.d.on_tracking(True); self.assertTrue(self.d.active()['tracking'])
        self.d.on_active_vision('scan'); self.assertTrue(self.d.active()['active_vision']); self.c.t += 121; self.assertFalse(self.d.active()['active_vision'])

    def test_replay_never_invents_and_expires(self):
        self.assertIsNone(self.d.replay_payload('follow'))
        self.d.on_follow(True); self.assertIs(self.d.replay_payload('follow'), True)
        self.d.on_follow(False); self.assertIs(self.d.replay_payload('follow'), False)     # latest wins: caller skips False
        self.d.on_tracking(True); self.c.t += 61; self.assertIsNone(self.d.replay_payload('tracking'))


class PlannerLogic(unittest.TestCase):
    def setUp(self):
        self.c = Clock(); self.cfg = dict(F.DEFAULTS); self.feat = {u: dict(v) for u, v in F.MANAGED.items()}
        self.p = F.Planner(self.cfg, self.feat, clock=self.c); self.all_on = {u: 'active' for u in self.feat}
        self.none = {k: False for k in F.TRIGGERS}; self.no_map = lambda: False

    def test_nothing_stopped_during_boot_grace(self):
        self.c.t += 299; self.assertEqual(self.p.decide(self.none, self.all_on, self.no_map), [])

    def test_idle_features_stopped_after_grace_and_idle(self):
        self.p.decide(self.none, self.all_on, self.no_map)                  # starts idle timers
        self.c.t += 301
        stops = sorted(u for a, u in self.p.decide(self.none, self.all_on, self.no_map) if a == 'stop')
        self.assertEqual(stops, sorted(self.feat))

    def test_needed_feature_started_and_kept(self):
        off = {u: 'inactive' for u in self.feat}; act = dict(self.none, follow=True)
        starts = sorted(u for a, u in self.p.decide(act, off, self.no_map) if a == 'start')
        self.assertEqual(starts, ['atlas-ai-annotator', 'atlas-follow-person', 'atlas-person-sensor-fusion'])

    def test_min_on_time_and_idle_reset(self):
        self.c.t += 400; self.p.note_started('atlas-agent-team')
        self.p.decide(self.none, self.all_on, self.no_map); self.c.t += 30
        self.assertNotIn(('stop', 'atlas-agent-team'), self.p.decide(self.none, self.all_on, self.no_map))

    def test_mapping_guard_blocks_tracker_and_follow_starts(self):
        off = {u: 'inactive' for u in self.feat}; act = dict(self.none, follow=True, tracking=True)
        starts = {u for a, u in self.p.decide(act, off, lambda: True) if a == 'start'}
        self.assertNotIn('atlas-follow-person', starts); self.assertNotIn('atlas-camera-tracker', starts)
        self.assertIn('atlas-ai-annotator', starts)

    def test_always_on_is_never_stopped(self):
        self.feat['atlas-agent-team']['always_on'] = True
        self.p.decide(self.none, self.all_on, self.no_map); self.c.t += 1000
        self.assertNotIn(('stop', 'atlas-agent-team'), self.p.decide(self.none, self.all_on, self.no_map))


class AllowlistAndConfig(unittest.TestCase):
    ESSENTIAL = ('atlas-voice-companion', 'atlas-local-llm', 'atlas-agent-supervisor', 'atlas-camera', 'rover-base-telemetry',
                 'atlas-cmd-vel-mux', 'atlas-ekf', 'atlas-localization', 'atlas-lidar', 'atlas-safety-status', 'atlas-sensor-recovery',
                 'atlas-mission-control', 'atlas-localization-monitor', 'rover-status-web', 'atlas-remote', 'atlas-tight-recovery')

    def test_allowlist_excludes_essential_services(self):
        self.assertFalse(set(F.MANAGED) & set(self.ESSENTIAL))
        src = (ROOT / 'scripts/atlas_feature_on_demand.py').read_text()
        for bad in ("'restart'", "'enable'", "'disable'", "'mask'"): self.assertNotIn(bad, src)

    def test_config_cannot_add_units_or_bad_triggers(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'c.yaml'
            p.write_text('features:\n  atlas-voice-companion: {idle_s: 60}\n')
            with self.assertRaises(SystemExit): F.load_config(str(p))
            p.write_text('features:\n  atlas-agent-team: {triggers: [motors]}\n')
            with self.assertRaises(SystemExit): F.load_config(str(p))
            p.write_text('features:\n  atlas-agent-team: {idle_s: 1, always_on: true}\n')
            cfg, feat = F.load_config(str(p)); self.assertEqual(feat['atlas-agent-team']['idle_s'], 30.0); self.assertTrue(feat['atlas-agent-team']['always_on'])

    def test_repo_config_loads(self):
        cfg, feat = F.load_config(str(ROOT / 'config/atlas_feature_on_demand.yaml'))
        self.assertEqual(set(feat), set(F.MANAGED)); self.assertEqual(cfg['boot_grace_s'], 300)

    def test_restore_all_starts_every_managed_unit(self):
        calls = []
        with mock.patch.object(F.subprocess, 'run', side_effect=lambda cmd, **k: calls.append(cmd) or mock.Mock(returncode=0, stdout='')):
            F.restore_all()
        self.assertEqual(sorted(c[3] for c in calls if c[2] == 'start'), sorted(u + '.service' for u in F.MANAGED))

    def test_unit_file_fail_open_and_no_boot_cycle(self):
        u = (ROOT / 'systemd/user/atlas-feature-on-demand.service').read_text()
        self.assertIn('ExecStopPost=', u); self.assertIn('restore-all', u); self.assertNotIn('After=default.target', u)


if __name__ == '__main__':
    unittest.main(verbosity=2)
