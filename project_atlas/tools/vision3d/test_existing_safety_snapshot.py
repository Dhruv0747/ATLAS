import tempfile
import time
import unittest
from pathlib import Path
from existing_safety_snapshot import publish,verify

def observations(t):
    return {'policy':[{'stop_latched':True,'manual_only':True,'commission_armed':False,'source':'STOPPED'},t],
            'command':[[0.0]*6,t],
            'encoders':[{'packet_fresh':True,'link_state':'LIVE','packet_age_s':.01,'encoder_interval_delta_m':[0]*4},t]}

class CacheTests(unittest.TestCase):
    def test_safe_and_failure_paths(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state.json';values=observations(10);publish(p,values,10,'boot')
            self.assertTrue(verify(p,10.1,'boot')['safe'])
            for now,boot in [(11,'boot'),(10.1,'wrong'),(9,'boot')]:
                with self.assertRaises(ValueError):verify(p,now,boot)
            for key,bad in [('command',[[0,1,0,0,0,0],10]),('policy',[{},10]),('encoders',[{},10])]:
                values=observations(10);values[key]=bad;publish(p,values,10,'boot')
                with self.assertRaises(ValueError):verify(p,10.1,'boot')
    def test_republishing_does_not_refresh_source(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'s';publish(p,observations(8),10,'boot')
            with self.assertRaises(ValueError):verify(p,10.1,'boot')
    def test_missing_malformed_and_zero_motion(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'s'
            with self.assertRaises(OSError):verify(p,10,'boot')
            p.write_text('broken')
            with self.assertRaises(ValueError):verify(p,10,'boot')
            values=observations(10);values['encoders'][0]['encoder_interval_delta_m'][2]=.01;publish(p,values,10,'boot')
            with self.assertRaises(ValueError):verify(p,10.1,'boot')
    def test_native_file_cost(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'s';start=time.process_time()
            for _ in range(1000):
                now=time.monotonic();publish(p,observations(now),now,'boot');verify(p,time.monotonic(),'boot')
            print('IPC_1000_WRITE_READ_CPU_SECONDS',time.process_time()-start)

if __name__=='__main__':unittest.main()
