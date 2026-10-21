"""Offline only: startup admission and bounded hashing; never opens camera."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import atlas_vision3d_runtime as R
from test_vision3d_stage31b_guard import Sim


class StartupCoverage(unittest.TestCase):
    def test_seed_accepts_elapsed_startup(self):
        self.assertEqual(R.validate_startup_sample([10,100,40],11.5),(10,(100,40)))

    def test_bad_seed_fails_closed(self):
        for seed in (None,[],[10,100,40],[13,100,40],[12,3,4],[12,float('nan'),0]):
            with self.subTest(seed=seed),self.assertRaises(ValueError):
                R.validate_startup_sample(seed,12.1)

    def test_first_cpu_failure_prevents_hardware(self):
        s=Sim(cpu=lambda i,w:78.8889 if i==0 else 60).run('concurrent')
        self.assertIsNone(s.launched_at)
        self.assertFalse(s.killed)
        self.assertEqual(s.state['state'],'RESOURCE BLOCKED')

    def test_initial_sensor_failure_prevents_hardware(self):
        def missing(i):raise RuntimeError('stale scan')
        s=Sim(extra_safety=missing).run('concurrent')
        self.assertIsNone(s.launched_at)
        self.assertIn('stale scan',s.state['reason'])

    def test_cpu_failure_inside_integrity_prevents_spawn(self):
        def slow_hash(root,checkpoint):
            for _ in range(30):
                R.time.sleep(0.1);checkpoint()
        with patch.object(R,'verify_runtime',side_effect=slow_hash):
            s=Sim(cpu=lambda i,w:77 if i==1 else 65).run('concurrent')
        self.assertIsNone(s.launched_at)
        self.assertEqual(s.state['state'],'RESOURCE BLOCKED')

    def test_stalled_integrity_fails_closed(self):
        def stall(root,checkpoint):
            R.time.sleep(2.1);checkpoint()
        with patch.object(R,'verify_runtime',side_effect=stall):
            s=Sim().run()
        self.assertIsNone(s.launched_at)
        self.assertIn('failing closed',s.state['reason'])

    def fixture(self,root):
        entries=[]
        for i in range(458):
            data=(b'abc'*100000 if i==0 else b'x')
            (root/str(i)).write_bytes(data)
            entries.append({'path':str(i),'sha256':hashlib.sha256(data).hexdigest()})
        (root/'manifest.json').write_text(json.dumps({'files':entries}))
        return entries

    def test_all_bytes_verified_with_bounded_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root);calls=[]
            with patch.object(R.time,'sleep'):
                R.verify_runtime(root,lambda:calls.append(True))
            self.assertGreater(len(calls),458*2)
            (root/'0').write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError,'integrity'),patch.object(R.time,'sleep'):
                R.verify_runtime(root,lambda:None)

    def test_cancellation_during_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root);calls=[]
            def cancel():
                calls.append(True)
                if len(calls)==4:raise RuntimeError('viewer paused')
            with self.assertRaisesRegex(RuntimeError,'paused'),patch.object(R.time,'sleep'):
                R.verify_runtime(root,cancel)
            self.assertEqual(len(calls),4)

    def test_duplicate_path_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);entries=self.fixture(root);entries[-1]=entries[0]
            (root/'manifest.json').write_text(json.dumps({'files':entries}))
            with self.assertRaisesRegex(ValueError,'duplicate'),patch.object(R.time,'sleep'):
                R.verify_runtime(root,lambda:None)

    def test_escape_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);entries=self.fixture(root);entries[0]['path']='../escape'
            (root/'manifest.json').write_text(json.dumps({'files':entries}))
            with self.assertRaisesRegex(ValueError,'unsafe'):
                R.verify_runtime(root,lambda:None)

    def test_manifest_count_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'manifest.json').write_text('{"files":[]}')
            with self.assertRaisesRegex(ValueError,'count'):
                R.verify_runtime(root,lambda:None)

    def test_parent_seeds_new_worker(self):
        s=R.ViewerSession()
        with patch.object(R.subprocess,'Popen') as popen,patch.object(R,'startup_sample',return_value=[10,100,20]):
            s.start('depth')
        self.assertEqual(json.loads(popen.call_args.kwargs['env'][R.STARTUP_SEED]),[10,100,20])


if __name__=='__main__':unittest.main()
