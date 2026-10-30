import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/vision3d'))
from calibration_capture import Evidence, Supervisor, safety, bundle


def observation(t):
    return dict(received_mono=t,cpu_window_s=1.,cpu=60.,ram=60.,temperature=63.,
                estop=True,manual_only=True,commissioning=False,recorder_off=True,
                telemetry_live=True,telemetry_age=.1,linear=0.,angular=0.,encoder_deltas=[0.]*4)


def frames(t):
    result={}
    for k in ('rgb','depth','rgb_info','depth_info'):
        m=dict(stamp_sec=100+t,stamp_nanosec=0,width=2,height=2,frame_id='test_optical_frame',cdr=b'original')
        if 'info' in k: m['k']=[2.,0.,1.,0.,2.,1.,0.,0.,1.]
        else: m.update(encoding='rgb8' if k=='rgb' else '16UC1',step=6 if k=='rgb' else 4,data_bytes=12 if k=='rgb' else 8,units_to_m=.001)
        result[k]=m
    return result


class CaptureTests(unittest.TestCase):
    def test_safety_failures(self):
        for key,value in [('estop',False),('linear',1),('telemetry_age',2),('cpu',75),
                          ('ram',80),('temperature',70),('temperature',float('nan')),
                          ('received_mono',-2),('cpu_window_s',3),('encoder_deltas',[1,0,0,0])]:
            with self.subTest(key=key):
                o=observation(0);o[key]=value
                with self.assertRaises(ValueError): safety(o,0)
        with self.assertRaises(KeyError): safety({},0)

    def test_complete_and_payload(self):
        with tempfile.TemporaryDirectory() as d:
            e=Evidence(Path(d)/'run');stop=Mock(return_value=True)
            expected={k:(2,2,'test_optical_frame') for k in frames(0)}
            s=Supervisor(0,e,stop,expected)
            for t in range(61): s.tick(t,observation(t),frames(t),(100+t)*10**9)
            r=json.loads((Path(d)/'run/result.json').read_text())
            self.assertEqual(r['status'],'COMPLETE');self.assertEqual(r['bundles'],60)
            self.assertEqual(r['sqlite_integrity'],'ok');stop.assert_called_once()
            self.assertEqual(r['calibration'],'UNVALIDATED')

    def test_timeout_stale_cleanup(self):
        for failure in ('missing','stale','cleanup','write','poll_timeout'):
            with self.subTest(failure=failure):
                store=Mock();stop=Mock(return_value=failure!='cleanup')
                s=Supervisor(0,store,stop,{k:(2,2,'test_optical_frame') for k in frames(0)})
                if failure=='missing':
                    for t in range(11): s.tick(t,observation(t))
                elif failure=='write':
                    store.write.side_effect=OSError('disk full')
                    s.tick(0,observation(0),frames(0),100*10**9)
                elif failure=='poll_timeout': s.tick(2,observation(0))
                else:
                    o=observation(0);o['telemetry_age']=10;s.tick(0,o)
                stop.assert_called_once();store.finish.assert_called_once()
                self.assertEqual(store.finish.call_args.args[0]['status'],'ABORTED')

    def test_bundle_rejections(self):
        expected={k:(2,2,'test_optical_frame') for k in frames(0)}
        for mode in ('missing','stale','skew','dimensions','units','info'):
            with self.subTest(mode=mode):
                m=frames(0)
                if mode=='missing':del m['rgb']
                if mode=='stale':m['depth']['stamp_sec']=99
                if mode=='skew':m['depth']['stamp_nanosec']=40000000
                if mode=='dimensions':m['depth']['width']=3
                if mode=='units':m['depth']['units_to_m']=1
                if mode=='info':m['rgb_info']['k'][0]=0
                with self.assertRaises(ValueError):bundle(m,100100000000,expected)


if __name__=='__main__':unittest.main()
