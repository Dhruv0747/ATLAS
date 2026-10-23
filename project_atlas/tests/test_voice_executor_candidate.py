import ast
import os
from pathlib import Path
import sys
import unittest
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/diagnostics'))
import benchmark_voice_executor as V

class VoiceCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw=Path(os.environ['ATLAS_CAPTURED_VOICE']).read_bytes()

    def test_inventory_preserves_types_raw_qos_timers(self):
        i=V.inventory(self.raw)
        self.assertEqual(len(i['subscriptions']),41)
        self.assertEqual(i['timers'],[5.0,1.0])
        raw=[s for s in i['subscriptions'] if s[3]]
        self.assertEqual(raw,[('LaserScan','/scan','sensor',True),('Imu','/im10a/imu/unvalidated','sensor',True)])
        self.assertTrue(all(s[2]==10 for s in i['subscriptions'] if not s[3]))

    def test_hash_rejects_different_source(self):
        with self.assertRaises(ValueError):V.patch_voice(self.raw+b'\n')

    def test_entire_voice_class_unchanged(self):
        def cls(raw):return next(n for n in ast.parse(raw).body if isinstance(n,ast.ClassDef))
        self.assertEqual(ast.dump(cls(self.raw)),ast.dump(cls(V.patch_voice(self.raw))))

    def test_byte_exact_rollback(self):
        patched=V.patch_voice(self.raw).decode()
        restored=patched.replace('from atlas_dashboard_executor import spin as _atlas_voice_spin\n','').replace('        _atlas_voice_spin(node)','        rclpy.spin(node)')
        self.assertEqual(restored.encode(),self.raw)

    def test_package_hash_and_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'candidate';m=V.prepare(self.raw,p)
            self.assertFalse(m['installed'])
            self.assertEqual((p/'atlas_voice_companion.original').read_bytes(),self.raw)
            self.assertEqual(V.hashlib.sha256((p/'atlas_voice_companion.py').read_bytes()).hexdigest(),m['candidate_sha256'])
            self.assertEqual(len(m['required_existing_files']),2)
            with self.assertRaises(FileExistsError):V.prepare(self.raw,p)

    def test_shutdown_finally_preserved(self):
        def final(raw):
            main=next(n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name=='main')
            return ast.dump(next(n for n in main.body if isinstance(n,ast.Try)))
        self.assertEqual(final(self.raw).replace("Attribute(value=Name(id='rclpy', ctx=Load()), attr='spin', ctx=Load())","Name(id='_atlas_voice_spin', ctx=Load())"),final(V.patch_voice(self.raw)))

    def test_real_period_timers_fire_and_executor_closes(self):
        if os.environ.get('ROS_LOCALHOST_ONLY')!='1' or os.environ.get('ROS_DOMAIN_ID')!='213':
            self.fail('isolated PC domain213 required')
        import rclpy
        from rclpy.context import Context
        raw=Path(os.environ['ATLAS_CAPTURED_EXECUTOR']).read_bytes()
        module=V.B.load_executor(V.B.cancellation_candidate(raw,True),'voice_timers')
        context=Context();rclpy.init(context=context)
        node=rclpy.create_node('offline_voice_timer_check',context=context)
        executor=module.SingleThreadedExecutor(context=context);executor.add_node(node)
        hits=[0,0]
        try:
            for i,period in enumerate(V.inventory(self.raw)['timers']):
                node.create_timer(period,lambda i=i:hits.__setitem__(i,hits[i]+1))
            deadline=V.time.monotonic()+5.25
            while V.time.monotonic()<deadline:executor.spin_once(timeout_sec=.05)
            self.assertGreaterEqual(hits[0],1);self.assertGreaterEqual(hits[1],5)
        finally:
            self.assertTrue(executor.shutdown(timeout_sec=1));node.destroy_node();context.shutdown()

if __name__=='__main__':unittest.main()
