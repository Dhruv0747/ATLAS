"""Mux worker/cleanup integration in a scratch Linux tree, with fake services."""
import os
import signal
import unittest
from unittest.mock import Mock

import test_mux_publisher_files as fixture
from mux_publisher_files import MuxFiles, Conflict, MUX, HELPER
from mux_publisher_transaction import worker_body, cleanup_body


@unittest.skipUnless(os.environ.get('ATLAS_MUX_TEST_ARCHIVE'), 'private reviewed fixture not supplied')
class MuxTransactionTest(unittest.TestCase):
    def setUp(self):
        fixture.MuxFilesTest.setUp(self)
        self.policy = Mock()
        self.pair = [4321, 8765]
        self.policy.restart.return_value = self.pair
        self.identity = Mock()
        self.accept = Mock()
        self.binding = {'boot_id': 'fixture-attempt', 'services': {}}  # verified per-attempt identity
        self.admission = Mock()

    def run_worker(self):
        return worker_body(self.policy, self.files, self.identity, self.accept, self.binding, self.admission)

    def test_success_uses_one_restart_and_accepts_the_replacement(self):
        self.run_worker()
        self.policy.restart.assert_called_once_with('activation')
        self.files.verify_installed(self.check)
        self.assertEqual(self.identity.before.call_args_list, [((self.binding,),)] * 2)   # around admission
        self.assertEqual(self.admission.call_args_list, [((self.policy,),), ((self.policy,), {'final': True})])
        self.accept.assert_called_once_with(self.policy, self.pair)
        self.policy.accept_new_process.assert_called_once_with(str(self.pair[0]))
        self.policy.restore_healthy.assert_called_once_with()

    def test_process_death_at_activation_then_separate_cleanup(self):
        # SIGKILL the scratch worker after file publication. No real systemd job.
        pid = os.fork()
        if pid == 0:
            try:
                self.policy.restart.side_effect=lambda phase: os.kill(os.getpid(), signal.SIGKILL)
                self.run_worker()
            finally:
                os._exit(71)
        _, status = os.waitpid(pid,0)
        self.assertTrue(os.WIFSIGNALED(status))
        self.assertEqual(os.WTERMSIG(status), signal.SIGKILL)
        recovered=MuxFiles(self.stage,self.tx,self.live)
        recovered.verify_installed(self.check)
        self.policy.cleanup.side_effect=lambda: recovered.verify_original(self.check)
        cleanup_body(self.policy, recovered)
        self.policy.quiesce_for_rollback.assert_called_once()
        self.policy.restart.assert_not_called()
        recovered.verify_original(self.check)
        self.policy.cleanup.assert_called_once()

    def test_failed_quiescence_preserves_candidate_and_controlled_policy(self):
        self.files.install(self.check)
        self.policy.quiesce_for_rollback.side_effect=TimeoutError('pending stop job')
        with self.assertRaises(TimeoutError):cleanup_body(self.policy,self.files)
        self.files.verify_installed(self.check)
        self.policy.cleanup.assert_not_called()
        self.policy.restart.assert_not_called()

    def test_stage_binding_drift_rejects_before_prepare(self):
        (self.stage/'binding.json').write_text('{}')
        with self.assertRaises(Conflict):self.run_worker()
        self.policy.prepare.assert_not_called()
        self.policy.restart.assert_not_called()
        self.assertFalse((self.live/HELPER).exists())
        self.assertEqual(self.original.read_bytes(), (self.stage/'rollback'/MUX).read_bytes())

    def test_final_admission_runs_after_install_and_before_restart(self):
        order=[]
        self.admission.side_effect=lambda p, final=False: order.append(('admit',final,self.policy.restart.called))
        self.run_worker()
        self.assertEqual(order,[('admit',False,False),('admit',True,False)])

    def test_unsafe_final_admission_prevents_restart(self):
        def admit(p, final=False):
            if final: raise ValueError('pre-admission unsafe: commands not zero')
        self.admission.side_effect=admit
        with self.assertRaisesRegex(ValueError,'pre-admission'):self.run_worker()
        self.policy.restart.assert_not_called()

    def test_unsafe_pre_admission_blocks_every_mutation(self):
        self.admission.side_effect=ValueError('pre-admission unsafe: control policy unsafe')
        with self.assertRaisesRegex(ValueError,'pre-admission'):self.run_worker()
        self.policy.prepare.assert_not_called()
        self.policy.restart.assert_not_called()
        self.assertFalse((self.live/HELPER).exists())
        self.files.verify_original(self.check)

    def test_service_identity_drift_blocks_unchanged_stage(self):
        self.identity.before.side_effect=Conflict('Mux identity drift')
        with self.assertRaises(Conflict):self.run_worker()
        self.policy.prepare.assert_not_called()
        self.policy.restart.assert_not_called()
        self.files.verify_original(self.check)

    def test_real_policy_reservation_and_file_rollback_on_lost_supervision(self):
        from test_mux_transaction_deadline import FakeMux
        from mux_restart_policy import UNIT
        clock=[100.]
        manager=dict(Id=UNIT,boot='fixture',safe=True,ActiveState='active',Restart='always',
                     MainPID='1000',start_ticks=4,Job='',operations=[])
        policy=FakeMux(self.tx,clock,manager)
        policy.begin_budget()
        def loss(controller, pair):
            manager['safe']=False
            controller.checkpoint()
        with self.assertRaisesRegex(ValueError,'maintenance protection'):
            worker_body(policy,self.files,self.identity,loss,self.binding,lambda p,final=False:None)
        recovered=FakeMux(self.tx,clock,manager)
        recovered.resume_budget(cleanup=True)
        cleanup_body(recovered,MuxFiles(self.stage,self.tx,self.live))
        self.files.verify_original(self.check)
        self.assertEqual(manager['operations'].count(('restart',UNIT)),1)
        self.assertEqual((manager['MainPID'],manager['Restart']),('0','always'))
        self.assertTrue(recovered.load()['restored'])
