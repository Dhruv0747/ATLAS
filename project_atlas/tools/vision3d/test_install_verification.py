import errno
import importlib.util
import json
import tempfile
import types
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
import install_verification as V


class Clock:
    def __init__(self):self.t=0
    def now(self):return self.t
    def sleep(self,n):self.t+=n


class VerificationTests(unittest.TestCase):
    def test_refused_then_ready(self):
        c=Clock();events=[];calls=[]
        values=[urllib.error.URLError(ConnectionRefusedError(errno.ECONNREFUSED,'refused')), {'ros':{}}]
        def fetch():
            x=values.pop(0)
            if isinstance(x,Exception):raise x
            return x
        self.assertEqual(V.wait_http_ready(fetch,lambda:calls.append(c.now()),clock=c.now,sleep=c.sleep,events=events),{'ros':{}})
        self.assertEqual(events[0]['safety'],'NOT_OBSERVED');self.assertEqual(len(calls),3)

    def test_readiness_deadline(self):
        c=Clock()
        def refused():raise urllib.error.URLError(ConnectionRefusedError(errno.ECONNREFUSED,'refused'))
        with self.assertRaises(TimeoutError):V.wait_http_ready(refused,lambda:None,timeout=1,clock=c.now,sleep=c.sleep)
        self.assertEqual(c.t,1)

    def test_no_wait_on_latched_cpu(self):
        with self.assertRaisesRegex(ValueError,'79.1453'):
            V.wait_http_ready(lambda:self.fail('must not fetch'),lambda:V.require_no_guard_failures(['CPU79.1453']))

    def test_api_failures_not_startup_delay(self):
        for error in [urllib.error.HTTPError('url',500,'failed',{},None),urllib.error.URLError(TimeoutError()),ValueError('malformed JSON')]:
            def fetch():raise error
            with self.subTest(error=error),self.assertRaises(type(error)):V.wait_http_ready(fetch,lambda:None)

    def test_malformed_status_rejected(self):
        for value in [None,[],{}, {'ros':None}]:
            with self.subTest(value=value),self.assertRaises(ValueError):V.wait_http_ready(lambda:value,lambda:None)

    def test_guard_failure_after_fetch(self):
        errors=[]
        def fetch():errors.append('CPU76');return {'ros':{}}
        with self.assertRaises(ValueError):V.wait_http_ready(fetch,lambda:V.require_no_guard_failures(errors))

    def test_off_false_requires_process_authority(self):
        r=V.verify_camera_off(lambda:{'state':'OFF','driver_stopped':False},lambda:[])
        self.assertFalse(r['reported_driver_stopped']);self.assertTrue(r['driver_absence_verified'])

    def test_conflicting_or_unknown_camera_rejected(self):
        for summary,inventory in [({'state':'OFF','driver_stopped':True},lambda:[{'pid':9}]),({'state':'ACTIVE'},lambda:[]),({},lambda:[])]:
            with self.assertRaises(ValueError):V.verify_camera_off(lambda:summary,inventory)

    def test_process_appears_between_observations(self):
        seq=iter([[],[{'pid':9}]])
        with self.assertRaises(ValueError):V.verify_camera_off(lambda:{'state':'OFF'},lambda:next(seq))

    def test_kernel_inventory(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'123';p.mkdir();(p/'comm').write_text('python3');(p/'cmdline').write_bytes(b'python3\0/a/atlas_vision3d_runtime.py\0--worker\0depth\0')
            self.assertEqual(V.camera_processes(root)[0]['pid'],123)
            (p/'cmdline').write_bytes(b'python3\0/a/atlas_status_web.py\0')
            self.assertEqual(V.camera_processes(root),[])
            (p/'comm').write_text('astra_camera_no')
            self.assertEqual(len(V.camera_processes(root)),1)
            (p/'cmdline').unlink()
            with self.assertRaises(ValueError):V.camera_processes(root)

    def test_error_preservation(self):
        r=V.failure_record('HTTP refused',['CPU79.15'],'rollback timeout')
        self.assertEqual(r,{'error':'HTTP refused','resource_guard_failures':['CPU79.15'],'rollback_error':'rollback timeout'})

    def test_saved_spike_precedes_candidate_start(self):
        # Exact retained trace and journal monotonic timestamps, no private telemetry.
        sample_end=22146.439868794;window=1.000281028002064
        old_stopping=22145.484842;old_stopped=22147.582186;new_started=22147.586605
        self.assertLess(sample_end-window,old_stopping)
        self.assertLess(sample_end,old_stopped)
        self.assertLess(sample_end,new_started)
        with self.assertRaises(ValueError):V.require_no_guard_failures(['CPU79.14529914529915 >75'])

    def test_simulated_transaction_restores_exact_files(self):
        # Entire installer runs against fake files/services/guards, never /proc or ROS.
        with tempfile.TemporaryDirectory() as d, patch.dict('sys.modules',{'stationary_gate':types.SimpleNamespace(preflight=lambda:None)}):
            spec=importlib.util.spec_from_file_location('offline_installer',Path(__file__).with_name('install_object_target_once.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
            m.STAGE=Path(d)/'stage';m.STAGE.mkdir();m.PKG=m.STAGE/'package';m.PKG.mkdir();m.LIVE=Path(d)/'live';m.LIVE.mkdir()
            for parent in ['candidate','rollback','scripts','config','web/v2']:(m.PKG/parent).mkdir(parents=True,exist_ok=True)
            for f,n in m.REPLACE.items():
                (m.LIVE/f).parent.mkdir(parents=True,exist_ok=True);(m.LIVE/f).write_bytes(b'original');(m.PKG/'rollback'/n).write_bytes(b'original');(m.PKG/'candidate'/n).write_bytes(b'candidate')
            (m.LIVE/'config').mkdir()
            for f in m.NEW:(m.PKG/f).write_text('{"enabled":false}' if f.endswith('.json') else 'candidate')
            for f in ['scripts/atlas_status_web.py','scripts/trt_yolo_detector.py','tools/vision3d/stationary_gate.py','web/v2/material.css','web/v2/vision3d.css']:
                (m.LIVE/f).parent.mkdir(parents=True,exist_ok=True);(m.LIVE/f).write_bytes(b'protected')
            (m.PKG/'SHA256SUMS').write_text(''.join(m.digest(p)+'  '+p.relative_to(m.PKG).as_posix()+'\n' for p in m.PKG.rglob('*') if p.is_file()))
            m.MANIFEST=m.digest(m.PKG/'SHA256SUMS');restarts=[]
            m.units=lambda:{'rover-status-web.service':{'ActiveState':'active'}}
            m.check=lambda:{'policy':{'stop_latched':True}}
            m.restart=lambda:restarts.append('web')
            def ready(errors,events,enforce=True):
                if enforce:raise ValueError('injected readiness failure')
            m.ready=ready;m.resource_monitor=lambda stop,errors,trace:None
            self.assertTrue(m.main());self.assertEqual(restarts,['web','web'])
            for f in m.REPLACE:self.assertEqual((m.LIVE/f).read_bytes(),b'original')
            for f in m.NEW:self.assertFalse((m.LIVE/f).exists())
            self.assertEqual(json.loads((m.STAGE/'result.json').read_text())['rollback'],'VERIFIED')
            with self.assertRaises(FileExistsError):m.main()

if __name__=='__main__':unittest.main()
