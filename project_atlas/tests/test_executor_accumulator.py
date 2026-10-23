import os
from pathlib import Path
import random
import sys
import unittest
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/diagnostics'))
import benchmark_executor_accumulator as A

class AccumulatorTests(unittest.TestCase):
    def values(self,obj):
        return tuple(getattr(obj,f) for f in A.B.FIELDS)
    def test_counts_right_unchanged_and_identity(self):
        from rclpy.waitable import NumberOfEntities as C
        rng=random.Random(28)
        for _ in range(2000):
            x,y=[C(*(rng.randrange(10000) for _ in range(6))) for _ in range(2)]
            right=self.values(y); expected=self.values(x+y)
            self.assertIs(A.accumulate(x,y),x)
            self.assertEqual(self.values(x),expected)
            self.assertEqual(self.values(y),right)

    def test_failure_atomic_all_fields(self):
        from rclpy.waitable import NumberOfEntities as C
        for f in A.B.FIELDS:
            x,y=C(1,2,3,4,5,6),C()
            setattr(y,f,'invalid'); before=self.values(x)
            with self.assertRaises(TypeError): A.accumulate(x,y)
            self.assertEqual(self.values(x),before)

    def test_wrong_source(self):
        with self.assertRaises(ValueError): A.candidate(b'wrong')

    def test_exact_only_count_block_changes(self):
        raw=Path(os.environ['ATLAS_CAPTURED_EXECUTOR']).read_bytes()
        baseline=A.B.cancellation_candidate(raw,True)
        candidate=A.candidate(raw)
        prefix,suffix=baseline.split(A.B.NEW)
        self.assertTrue(candidate.startswith(prefix))
        self.assertTrue(candidate.endswith(suffix))
        self.assertEqual(candidate.count('added_count = waitable.get_num_entities()'),1)

    def test_package_and_byte_exact_rollback_copy(self):
        raw=Path(os.environ['ATLAS_CAPTURED_EXECUTOR']).read_bytes()
        adapter=(Path(__file__).resolve().parents[1]/'scripts/atlas_dashboard_executor.py').read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'candidate'
            m=A.package(raw,adapter,out)
            self.assertFalse(m['installed'])
            self.assertEqual((out/'adapter.original').read_bytes(),adapter)
            self.assertEqual((out/'implementation.original').read_bytes(),A.B.cancellation_candidate(raw,True).encode())
            for name,sha in m['files'].items():
                self.assertEqual(A.hashlib.sha256((out/name).read_bytes()).hexdigest(),sha)
            with self.assertRaises(FileExistsError): A.package(raw,adapter,out)
            with self.assertRaises(ValueError): A.package(raw,adapter+b'\n',Path(tmp)/'wrong')
            self.assertFalse((Path(tmp)/'wrong').exists())

if __name__=='__main__': unittest.main()
