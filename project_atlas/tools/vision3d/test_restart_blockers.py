import json
import tempfile
import unittest
from pathlib import Path
from restart_safety_observer import Safety,read_observer,atomic


def feed(s,t=10):
    s.receive('policy',{'stop_latched':True,'manual_only':True,'commission_armed':False,'source':'STOPPED'},t)
    s.receive('command',[0.0]*6,t)
    s.receive('encoders',{'packet_fresh':True,'link_state':'LIVE','packet_age_s':.01,'encoder_interval_delta_m':[0.0]*4},t)


class SafetyTests(unittest.TestCase):
    def test_http_independent(self):
        s=Safety();feed(s);self.assertTrue(s.evaluate(10.1)['safe'])
    def test_loss_latches(self):
        s=Safety();feed(s);s.evaluate(10.1);self.assertFalse(s.evaluate(11.1)['safe']);feed(s,12);self.assertFalse(s.evaluate(12)['safe'])
    def test_unsafe(self):
        for key,value in [('policy',{}),('policy',None),('command',[0,1,0,0,0,0]),('command',[float('nan')]*6),('encoders',{})]:
            s=Safety();feed(s);s.evaluate(10);s.receive(key,value,10)
            self.assertFalse(s.evaluate(10.1)['safe'])
    def test_nonce_stale_or_dead_observer(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'s.json';atomic(p,{'safe':True,'nonce':'a','mono':10})
            self.assertTrue(read_observer(p,'a',10.5)['safe'])
            for nonce,now in [('b',10),('a',11),('a',9)]:
                with self.assertRaises(ValueError):read_observer(p,nonce,now)
    def test_missing(self):self.assertFalse(Safety().evaluate(10)['safe'])

if __name__=='__main__':unittest.main()
