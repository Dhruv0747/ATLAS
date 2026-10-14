import unittest
from stage20_capture import Timing
class TimingTests(unittest.TestCase):
    def test_constant_memory_histogram(self):
        t=Timing()
        for v in (0,.004,.2,2.):t.add(v)
        s=t.summary();self.assertEqual(s['count'],4);self.assertEqual(sum(s['bucket_counts']),4)
        self.assertEqual(s['max_s'],2.);self.assertEqual(len(s['bucket_counts']),8)
    def test_empty_not_nonfinite(self):
        self.assertEqual(Timing().summary()['mean_s'],0.)
if __name__=='__main__':unittest.main()
