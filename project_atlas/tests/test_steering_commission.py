import sys
import tempfile
import time
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from atlas_steering_commission import SteeringCommission

DEFAULTS={'front': {'center':90,'left':121,'right':50},'rear':{'center':90,'left':134,'right':64}}
class SteeringTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'steering.json'
        self.c=SteeringCommission(self.path,DEFAULTS)
        self.seq=0
        self.applied={'front':90,'rear':90}
    def tearDown(self):
        while self.c.saving: time.sleep(.01)
        self.tmp.cleanup()
    def send(self,op,**kwargs):
        self.seq+=1
        self.c.command(dict(op=op,session='a'*32,seq=self.seq,**kwargs),0,self.applied,True)
    def enter(self): self.send('enter',lifted=True)
    def test_requires_confirmation(self):
        with self.assertRaises(ValueError): self.send('enter')
        self.assertFalse(self.c.locked)
    def test_requires_stop(self):
        with self.assertRaises(ValueError): self.c.command({'op':'enter','session':'a'*32,'seq':1,'lifted':True},0,self.applied,False)
    def test_enter_no_movement(self):
        self.enter();self.assertEqual(self.c.targets,self.applied)
    def test_independent_jog(self):
        self.enter();self.send('jog',side='front',step=5)
        self.assertEqual(self.c.targets,{'front':95,'rear':90})
    def test_clamp(self):
        self.enter()
        for _ in range(40): self.send('jog',side='rear',step=-5)
        self.assertEqual(self.c.targets['rear'],64)
    def test_front_left_calibration_extension_only(self):
        self.enter()
        for _ in range(40): self.send('jog',side='front',step=5)
        self.assertEqual(self.c.targets['front'],126)
        self.assertEqual(self.c.saved['front']['left'],121)
        self.assertEqual(self.c.envelope['rear'],DEFAULTS['rear'])
    def test_expiry_freezes_keeps_traction_locked(self):
        self.enter();self.send('jog',side='front',step=5)
        self.c.tick(2,self.applied,True)
        self.assertTrue(self.c.locked);self.assertIsNone(self.c.token)
        self.assertEqual(self.c.targets,self.applied)
        with self.assertRaises(ValueError):self.send('jog',side='front',step=1)
    def test_stop_priority(self):
        self.enter();self.c.freeze(self.applied,'B');self.assertIsNone(self.c.token)
    def test_competing_session(self):
        self.enter()
        with self.assertRaises(ValueError): self.c.command({'op':'enter','session':'b'*32,'seq':2,'lifted':True},0,self.applied,True)
    def test_invalid_step(self):
        self.enter()
        with self.assertRaises(ValueError): self.send('jog',side='front',step=30)
    def test_replayed_sequence(self):
        self.enter()
        with self.assertRaises(ValueError):self.c.command({'op':'heartbeat','session':'a'*32,'seq':1},0,self.applied,True)
    def test_save_reload(self):
        self.enter();self.applied['front']=91;self.c.targets['front']=91
        self.send('mark',side='front',point='center');self.send('save',confirmed=True)
        while self.c.saving:time.sleep(.01)
        self.assertEqual(SteeringCommission(self.path,DEFAULTS).saved['front']['center'],91)
    def test_invalid_limits(self):
        self.enter();self.c.draft['front']['center']=130
        with self.assertRaises(ValueError):self.send('save',confirmed=True)
        self.assertFalse(self.path.exists())
    def test_mark_wait_settle(self):
        self.enter();self.send('jog',side='front',step=5)
        with self.assertRaises(ValueError):self.send('mark',side='front',point='center')
    def test_exit_explicit(self):
        self.enter();self.send('exit');self.assertFalse(self.c.locked)
    def test_reset_preserves_targets_saved_and_lock(self):
        self.enter();self.send('jog',side='front',step=5)
        self.c.draft['front']['center']=50
        self.send('reset_draft')
        self.assertEqual(self.c.draft,DEFAULTS)
        self.assertEqual(self.c.saved,DEFAULTS)
        self.assertEqual(self.c.targets['front'],95)
        self.assertTrue(self.c.locked)

if __name__=='__main__':unittest.main()
