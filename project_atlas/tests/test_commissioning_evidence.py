"""Pure offline tests. No ROS, serial, actuator or network imports."""
import json
import importlib.util
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
from atlas_commissioning_evidence import EvidenceLedger, readiness
from atlas_commissioning import Console


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)/'project_atlas'
        (self.root/'scripts').mkdir(parents=True)
        (self.root/'config').mkdir()
        (self.root/'scripts/yahboom_base.py').write_text('FRONT_STEER_CENTER = 90\n')
        self.db=self.root/'evidence.sqlite3'
        self.ledger=EvidenceLedger(self.root,self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def row(self,gate):
        return next(r for r in self.ledger.current() if r['gate']==gate)

    def passed(self,gate='steering_front'):
        return self.ledger.record(gate,'PASS',{'points':[50,90,121]},'test fixture','Operator fixture')

    def test_new_ledger_never_implies_ready(self):
        r=readiness(self.ledger.current(),{})
        self.assertEqual(r['state'],'AUTONOMY BLOCKED')
        self.assertEqual(r['current_step'],'steering_front')
        self.assertFalse(r['physical_tests_automatically_started'])
        self.assertFalse(r['fallback']['resume_authorized'])

    def test_valid_pass_survives_restart_and_skips_gate(self):
        self.passed()
        self.ledger=EvidenceLedger(self.root,self.db)
        r=readiness(self.ledger.current(),{})
        self.assertIn('steering_front',r['completed'])
        self.assertEqual(r['current_step'],'steering_rear')

    def test_unrelated_ui_change_does_not_invalidate_encoder(self):
        self.passed('encoder_metric')
        (self.root/'scripts/atlas_status_web.py').write_text('# label change')
        self.assertEqual(self.row('encoder_metric')['status'],'PASS')

    def test_relevant_change_requires_retest_with_reason(self):
        self.passed()
        (self.root/'scripts/yahboom_base.py').write_text('FRONT_STEER_CENTER = 95\n')
        r=self.row('steering_front')
        self.assertEqual(r['status'],'RETEST_REQUIRED')
        self.assertIn('scripts/yahboom_base.py',r['invalidated_by'])
        self.assertTrue(r['retest_reason'])

    def test_same_geometry_resave_and_other_axle_do_not_invalidate(self):
        path=self.root/'config/steering_calibration.json'
        cfg={'saved_at':1,'steering':{'front':{'center':90,'left':121,'right':50},'rear':{'center':90,'left':134,'right':64}}}
        path.write_text(json.dumps(cfg))
        self.passed()
        cfg['saved_at']=2;cfg['steering']['rear']['center']=92
        path.write_text(json.dumps(cfg))
        self.assertEqual(self.row('steering_front')['status'],'PASS')

    def test_journal_bounded_latest_pass_pinned(self):
        first=self.passed()
        for i in range(510):
            self.ledger.record('telemetry_hardware','OBSERVED',{'i':i},'unit test')
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM evidence').fetchone()[0],500)
        self.assertEqual(self.row('steering_front')['test_id'],first['test_id'])
        self.assertEqual(len(self.ledger.history()),100)

    def test_legacy_migration_is_idempotent_and_not_physical_pass(self):
        legacy=self.root/'legacy.sqlite3'
        with closing(sqlite3.connect(legacy)) as db:
            db.execute('CREATE TABLE results (id INTEGER PRIMARY KEY, payload TEXT)')
            db.execute('INSERT INTO results(payload) VALUES (?)',(json.dumps({'kind':'hardware','state':'PASS'}),))
            db.commit()
        self.ledger=EvidenceLedger(self.root,legacy)
        self.assertEqual(self.row('telemetry_hardware')['status'],'OBSERVED')
        self.ledger=EvidenceLedger(self.root,legacy)
        self.assertEqual(len(self.ledger.history()),1)

    def test_historical_directions_retained_without_new_precision_claim(self):
        docs=self.root.parent/'docs';docs.mkdir()
        (docs/'THREE_ENCODER_GROUND_OBSERVATION_2026-09-17.md').write_text('fixture')
        self.ledger.import_direction_observation()
        self.ledger.import_direction_observation()
        r=self.row('encoder_direction')
        self.assertEqual(r['status'],'OBSERVED')
        self.assertIsNone(r['configuration_hash'])
        self.assertEqual(len(self.ledger.history()),1)
        self.passed('steering_front');self.passed('steering_rear')
        self.assertEqual(readiness(self.ledger.current(),{})['current_step'],'encoder_metric')

    def test_hardware_invalidation_persists_and_race_rejected(self):
        old=self.passed()
        new=self.ledger.invalidate('steering_front','Replaced steering linkage',old['test_id'])
        self.assertEqual(new['invalidated_by'],old['test_id'])
        self.assertEqual(self.row('steering_front')['status'],'RETEST_REQUIRED')
        with self.assertRaises(ValueError):
            self.ledger.invalidate('steering_front','Concurrent outdated edit',old['test_id'])

    def test_interrupted_test_never_passes(self):
        self.ledger.record('encoder_metric','IN_PROGRESS',{},'fixture')
        self.assertEqual(self.row('encoder_metric')['status'],'RETEST_REQUIRED')

    def test_current_observation_not_mistaken_for_interruption(self):
        self.ledger.record('telemetry_imu','IN_PROGRESS',{'observation_id':'live'},'fixture')
        r=next(r for r in self.ledger.current('live') if r['gate']=='telemetry_imu')
        self.assertEqual(r['status'],'IN_PROGRESS')

    def test_new_console_history_empty_not_error(self):
        c=Console(self.root,self.db,lambda:{})
        self.assertEqual(c.history(),[])

    @unittest.skipUnless(importlib.util.find_spec('yaml'), 'PyYAML provided by ROS runtime')
    def test_m4_configuration_is_excluded_not_a_physical_pass(self):
        (self.root/'config/encoder_selection.yaml').write_text('excluded_encoders: [4]\nnavigation_validated: false\n')
        self.ledger.import_configured_exclusion()
        self.ledger.import_configured_exclusion()
        self.assertEqual(self.row('m4_feedback')['status'],'EXCLUDED')
        self.assertEqual(len(self.ledger.history()),1)

    def test_arbitrary_state_gate_nonfinite_and_empty_pass_rejected(self):
        for gate,status,measure in [('bad','PASS',{}),('encoder_metric','OK',{}),('encoder_metric','PASS',{}),('encoder_metric','OBSERVED',{'x':float('nan')})]:
            with self.assertRaises(ValueError):
                self.ledger.record(gate,status,measure,'fixture')

    def test_storage_corruption_fails_closed(self):
        corrupt=self.root/'bad.sqlite3';corrupt.write_text('not SQLite')
        c=Console(self.root,corrupt,lambda:{})
        with self.assertRaises(ValueError):c.evidence()
        with self.assertRaises(ValueError):c.start('hardware')
        self.assertIsNone(c.active)

    def console_saved(self):
        cfg={'front':{'center':90,'left':121,'right':50},'rear':{'center':90,'left':134,'right':64}}
        (self.root/'config/steering_calibration.json').write_text(json.dumps({'saved_at':123,'steering':cfg}))
        self.data={'steering_calibration':{'age':0,'value':json.dumps({'saved':cfg,'saving':False,'error':''})},
                   'control_policy':{'age':0,'value':json.dumps({'stop_latched':True})}}
        return Console(self.root,self.db,lambda:self.data)

    def test_steering_witness_needs_saved_file_and_live_owner(self):
        c=Console(self.root,self.db,lambda:{})
        h=c.ledger.signature('steering_front')['hash']
        with self.assertRaises(ValueError):c.confirm_steering('front',h,'All three points verified')
        c=self.console_saved();h=c.ledger.signature('steering_front')['hash']
        result=c.confirm_steering('front',h,'All three physical points checked safely')
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(result['measurements']['physical_feedback'],'NOT INSTALLED')

    def test_witness_stale_hash_stale_owner_mismatch_and_unlatched_stop_rejected(self):
        c=self.console_saved();h=c.ledger.signature('steering_front')['hash']
        with self.assertRaises(ValueError):c.confirm_steering('front','old','Verified all physical points')
        self.data['steering_calibration']['age']=3
        with self.assertRaises(ValueError):c.confirm_steering('front',h,'Verified all physical points')
        self.data['steering_calibration']['age']=0
        self.data['control_policy']['value']='{"stop_latched":false}'
        with self.assertRaises(ValueError):c.confirm_steering('front',h,'Verified all physical points')
        self.data['control_policy']['value']='{"stop_latched":true}'
        self.data['steering_calibration']['value']='{"saved":{},"saving":false}'
        with self.assertRaises(ValueError):c.confirm_steering('front',h,'Verified all physical points')

    def test_no_hardware_or_actuation_path_in_evidence_module(self):
        source=(SCRIPTS/'atlas_commissioning_evidence.py').read_text(encoding='utf-8')
        for forbidden in ('import serial','create_publisher(', 'Rosmaster(', 'subprocess', 'os.system'):
            self.assertNotIn(forbidden,source)


if __name__=='__main__':unittest.main()
