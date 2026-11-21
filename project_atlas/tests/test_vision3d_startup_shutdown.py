"""Offline lifecycle regressions: no camera or production ROS connection."""
import importlib.util
from pathlib import Path
import signal
import subprocess
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('startup_runtime',ROOT/'scripts/atlas_vision3d_runtime.py')
R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)


class StartupShutdown(unittest.TestCase):
    def test_signal_before_context_kept(self):
        text='[INFO] [1792596273.308090013] [rclcpp]: signal_handler(SIGINT/SIGTERM)\n[ERROR] [1792596273.334964466] failed: context is invalid'
        result=R.driver_error_order(text)
        self.assertTrue(result['signal_precedes_invalid_context'])
        self.assertAlmostEqual(result['context_after_signal_ms'],26.874,places=2)
        self.assertEqual(len(R.negotiation_lines(text)),2)

    def test_independent_error_not_classified_as_cancel(self):
        for text in ('[ERROR] [1.0] context is invalid',
                     '[ERROR] [1.0] context is invalid\n[INFO] [2.0] signal_handler(SIGINT/SIGTERM)'):
            self.assertFalse(R.driver_error_order(text)['signal_precedes_invalid_context'])

    def test_cancel_during_start_reaps(self):
        child=Mock(pid=123,returncode=-2);child.poll.side_effect=[None,-2]
        state={}
        with patch.object(R.os,'killpg') as kill:
            self.assertTrue(R.shutdown_owned_process(child,state,'driver'))
        kill.assert_called_once_with(123,signal.SIGINT);child.wait.assert_called_once_with(timeout=2)

    def test_exit_race_does_not_lose_cleanup(self):
        child=Mock(pid=123,returncode=0);child.poll.side_effect=[None,0]
        with patch.object(R.os,'killpg',side_effect=ProcessLookupError):
            self.assertTrue(R.shutdown_owned_process(child,{},'driver'))

    def test_stuck_child_escalates_and_reaps(self):
        child=Mock(pid=123,returncode=-9);child.poll.side_effect=[None,-9]
        child.wait.side_effect=[subprocess.TimeoutExpired('driver',2),-9]
        with patch.object(R.os,'killpg') as kill:
            self.assertTrue(R.shutdown_owned_process(child,{},'driver'))
        self.assertEqual([x.args[1] for x in kill.call_args_list],[signal.SIGINT,signal.SIGKILL])

    def test_cpu_failure_evidence_precedes_shutdown(self):
        state={};R.lifecycle_event(state,'resource_guard_failed',evidence={'cpu':78.4615})
        child=Mock(pid=123,returncode=-2);child.poll.side_effect=[None,-2]
        with patch.object(R.os,'killpg'):R.shutdown_owned_process(child,state,'driver')
        self.assertEqual([x['event'] for x in state['lifecycle']],['resource_guard_failed','signal_send','process_reaped'])
        self.assertTrue(all('monotonic_s' in x and 'unix_s' in x for x in state['lifecycle']))

    def test_bounded_metadata(self):
        state={}
        for i in range(100):R.lifecycle_event(state,'example')
        self.assertEqual(len(state['lifecycle']),32)

    def test_limits_and_domain_preserved(self):
        self.assertEqual(R.driver_env({})['ROS_DOMAIN_ID'],'77')
        self.assertEqual(R.MIN_CPU_WINDOW_S,1)
        for values in ((75.01,60,60),(70,80.01,60),(70,60,70.01)):
            with self.assertRaises(ValueError):R.limits(*values)

    def test_mode_configuration(self):
        for mode in ('depth','ir','concurrent'):
            args=R.driver_args(mode)
            self.assertIn('enable_point_cloud:=false',args)
            self.assertIn('enable_colored_point_cloud:=false',args)
            self.assertIn('use_uvc_camera:='+str(mode=='concurrent').lower(),args)
        self.assertIn('ir_width:=640',R.driver_args('ir'))
        self.assertIn('depth_width:=160',R.driver_args('depth'))


if __name__=='__main__':unittest.main()
