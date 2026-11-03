"""Short real-clock checks for the outer transaction limit. No real rover units."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import mux_publisher_transaction as tx


class OuterDeadline(unittest.TestCase):
    def test_blocked_io_worker_and_new_cleanup_share_launch_time(self):
        prefix = """import os,time,sys
import mux_publisher_transaction as t
t.MuxPolicy.WORKER_SECONDS=.36
t.MuxPolicy.CLEANUP_SECONDS=.36
def blocked(cleaning,start,entered):time.sleep(9)
t._run_phase=blocked
t.run_phase(sys.argv[1]=='cleanup')
"""
        origin=tx.MuxPolicy.now()
        env=dict(os.environ,ATLAS_MUX_ORIGIN_BOOTTIME=repr(origin))
        for phase in ('worker','cleanup'):
            result=subprocess.run([sys.executable,'-B','-c',prefix,phase],cwd=Path(tx.__file__).parent,
                                  env=env,timeout=2,capture_output=True)
            self.assertEqual(result.returncode,-signal.SIGALRM,result.stderr)
        elapsed=tx.MuxPolicy.now()-origin
        self.assertGreaterEqual(elapsed,.7)
        self.assertLess(elapsed,.97)

    def test_expired_origin_refuses_before_journal_read(self):
        past=tx.MuxPolicy.now()-91
        with patch.dict(os.environ,ATLAS_MUX_ORIGIN_BOOTTIME=str(past)), patch.object(tx,'_run_phase') as run:
            with self.assertRaises(TimeoutError):tx.run_phase(True)
            run.assert_not_called()

    def test_transient_unit_contains_one_cleanup_and_one_origin(self):
        args=tx.transient_command()
        self.assertIn('--property=Restart=no',args)
        self.assertIn('--property=KillMode=control-group',args)
        self.assertEqual(sum('ExecStopPost=' in a for a in args),1)
        self.assertEqual(sum('ATLAS_MUX_ORIGIN_BOOTTIME=' in a for a in args),1)

    def test_resource_guard_rejects_exact_cpu_limit(self):
        with patch.object(tx.MuxPolicy,'now',side_effect=[3.,4.]), patch.object(tx,'ticks',side_effect=[(0,0),(100,25)]),patch.object(tx,'resources',return_value=(50,{k:55 for k in tx.THERMAL})):
            with self.assertRaisesRegex(ValueError,'strict resource'):tx.ResourceSamples().check()


class SourceAcceptance(unittest.TestCase):
    def setUp(self):
        self.payload={'stop_latched':True,'manual_only':True,'commission_armed':False,
                      'source':'STOPPED','source_provenance':{'pid':5,'start_ticks':2,'boot_id':'b',
                      'sequence':4,'observed_mono':10.02},'published_command':{'sequence':3,
                      'published_mono':10.0,'values':[0]*6}}
        self.encoder={'packet_fresh':True,'packet_age_s':.02,'link_state':'LIVE',
                      'encoder_interval_delta_m':[0]*4,'encoder_packet_monotonic':10.01}
        self.data={'boot_id':'b','published_mono':10.05,'observations':{
            'policy':[self.payload,10.04],'encoders':[self.encoder,10.03],'command':[[0]*6,10.025]}}
        self.consumer=tx.SourceConsumer('b',{'policy':('b',5,2)})

    def test_source_and_later_callback_both_fresh(self):
        self.assertEqual(tx.check_envelope(self.consumer,self.data,10.08,None),self.payload)

    def test_fresh_republication_cannot_revive_stale_raw_packet(self):
        self.encoder['encoder_packet_monotonic']=8.99
        with self.assertRaisesRegex(ValueError,'encoder source expired'):
            tx.check_envelope(self.consumer,self.data,10.08,None)

    def test_command_mirror_cannot_be_revived_by_later_receipt(self):
        self.payload['published_command']['published_mono']=9.0
        with self.assertRaisesRegex(ValueError,'command/source stale'):
            tx.check_envelope(self.consumer,self.data,10.08,self.payload)
