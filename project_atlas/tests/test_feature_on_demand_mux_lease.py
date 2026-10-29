"""Feature manager vs an authorised mux restart (Stage 29, 2026-10-29): a stale control policy during a VALID mux
maintenance lease keeps the last fresh verdict; everything else behaves exactly as before."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import atlas_feature_on_demand as F      # noqa: E402
import atlas_base_maintenance as bm      # noqa: E402


class Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


MANUAL = json.dumps({'manual_only': True, 'source': 'STOPPED'})


def demand(maint):
    c = Clock()
    d = F.Demand(dict(F.DEFAULTS), clock=c, maintenance=lambda: maint[0])
    d.on_mission('READY')
    return d, c


class DemandDuringMuxRestart(unittest.TestCase):
    def test_without_lease_stale_policy_is_autonomy_as_before(self):
        maint = [False]; d, c = demand(maint)
        d.on_policy(MANUAL); self.assertFalse(d.active()['autonomy'])
        c.t += 6.0; d.on_mission('READY')
        self.assertTrue(d.active()['autonomy']); self.assertFalse(d.held)

    def test_valid_lease_holds_last_fresh_verdict_then_grace_ends(self):
        maint = [True]; d, c = demand(maint)
        d.on_policy(MANUAL)
        for dt in (6.0, 30.0, 60.0):
            c.t = 1000.0 + dt; d.on_mission('READY')
            self.assertFalse(d.active()['autonomy'], dt); self.assertTrue(d.held)
        c.t = 1000.0 + F.DEFAULTS['policy_stale_s'] + F.DEFAULTS['mux_restart_grace_s'] + 0.5; d.on_mission('READY')
        self.assertTrue(d.active()['autonomy']); self.assertFalse(d.held)       # bounded: fail-open again

    def test_lease_never_hides_a_genuine_autonomy_request(self):
        maint = [True]; d, c = demand(maint)
        d.on_policy(json.dumps({'manual_only': False}))
        self.assertTrue(d.active()['autonomy'])                                  # fresh, real request
        c.t += 10.0; d.on_mission('READY')
        self.assertTrue(d.active()['autonomy'])                                  # stale: last verdict was autonomy
        d.on_policy(MANUAL); c.t += 1.0; d.on_mission('PLANNING')
        self.assertTrue(d.active()['autonomy'])                                  # mission not READY still triggers

    def test_fresh_start_under_lease_waits_then_fails_open(self):
        maint = [True]; c = Clock()
        d = F.Demand(dict(F.DEFAULTS), clock=c, maintenance=lambda: maint[0])     # nothing received yet
        self.assertFalse(d.active()['autonomy']); self.assertTrue(d.held)
        c.t += F.DEFAULTS['mux_restart_grace_s'] + 0.5
        self.assertTrue(d.active()['autonomy'])                                   # grace over: fail-open as before
        maint[0] = False; c.t = 1000.0
        d2 = F.Demand(dict(F.DEFAULTS), clock=c, maintenance=lambda: maint[0])
        self.assertTrue(d2.active()['autonomy'])                                  # no lease: fail-open at once

    def test_mission_stale_under_lease_keeps_last_mission_verdict(self):
        maint = [True]; d, c = demand(maint)
        d.on_policy(MANUAL); c.t += F.DEFAULTS['mission_stale_s'] + 2.0; d.on_policy(MANUAL)
        self.assertFalse(d.active()['autonomy'])                                  # last mission READY
        d.on_mission('PLANNING'); c.t += F.DEFAULTS['mission_stale_s'] + 2.0; d.on_policy(MANUAL)
        self.assertTrue(d.active()['autonomy'])                                   # last mission was not READY

    def test_lease_ending_mid_restart_returns_to_fail_open(self):
        maint = [True]; d, c = demand(maint)
        d.on_policy(MANUAL); c.t += 8.0; d.on_mission('READY')
        self.assertFalse(d.active()['autonomy'])
        maint[0] = False
        self.assertTrue(d.active()['autonomy'])

    def test_planner_starts_nothing_while_held(self):
        maint = [True]; d, c = demand(maint)
        cfg, feats = F.load_config(None)
        plan = F.Planner(cfg, feats, clock=c)
        d.on_policy(MANUAL)
        state = {u: 'inactive' for u in feats}
        c.t += 7.0; d.on_mission('READY')
        self.assertEqual(plan.decide(d.active(), state, lambda: False), [])
        maint[0] = False                                                          # same instant, no lease
        starts = {u for a, u in plan.decide(d.active(), state, lambda: False) if a == 'start'}
        self.assertEqual(starts, {u for u, f in feats.items() if 'autonomy' in f['triggers']})


class LeaseView(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp()) / 'atlas-mux-maintenance'

    def test_view_follows_the_real_lease_states(self):
        view = F.mux_maintenance_view(root=self.root, ttl_s=0.0)
        self.assertFalse(view())                                                  # NONE
        m = bm.Maintenance(root=self.root)
        s = m.arm('test mux restart', 60.0)
        self.assertTrue(view())                                                   # ACTIVE
        m.release(s); m.clear(s)
        self.assertFalse(view())                                                  # gone

    def test_owner_gone_or_corrupt_is_not_active(self):
        view = F.mux_maintenance_view(root=self.root, ttl_s=0.0)
        p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
        try:
            m = bm.Maintenance(root=self.root); m.arm('owned by a short-lived process', 60.0, owner_pid=p.pid)
            self.assertTrue(view())
        finally:
            p.kill(); p.wait()
        self.assertFalse(view())                                                  # INVALID: owner gone
        (self.root / 'lease.json').write_text('{not json')
        self.assertFalse(view())                                                  # INVALID: corrupt

    def test_view_caches_reads(self):
        view = F.mux_maintenance_view(root=self.root, ttl_s=30.0)
        self.assertFalse(view())
        s = bm.Maintenance(root=self.root).arm('cached', 60.0)
        self.assertFalse(view())                                                  # within ttl: cached value
        bm.Maintenance(root=self.root).release(s)

    def test_restore_all_skipped_only_under_a_valid_lease(self):
        calls = []
        orig = F.systemctl
        F.systemctl = lambda *a, **k: calls.append(a) or type('R', (), {'returncode': 0, 'stdout': ''})()
        orig_view = F.mux_maintenance_view
        try:
            F.mux_maintenance_view = lambda root=None, ttl_s=1.0: (lambda: True)
            F.restore_all(); self.assertEqual(calls, [])
            F.mux_maintenance_view = lambda root=None, ttl_s=1.0: (lambda: False)
            F.restore_all(); self.assertEqual(sorted(a[1] for a in calls), sorted(u + '.service' for u in F.MANAGED))
        finally:
            F.systemctl = orig; F.mux_maintenance_view = orig_view

    def test_source_keeps_the_allowlist_and_fail_open(self):
        src = (ROOT / 'scripts/atlas_feature_on_demand.py').read_text()
        self.assertIn("'policy_stale_s': 5.0", src); self.assertIn('def restore_all', src)
        self.assertIn("'mux_restart_grace_s': 60.0", src)
        self.assertNotIn('arm(', src.split('def mux_maintenance_view')[1].split('return active')[0])   # read only


if __name__ == '__main__':
    unittest.main()
