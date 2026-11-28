import copy
import math
import unittest
from stage20_compare import compare_ekf,compare_amcl,AMCL_MARGINS

def row(t=1000000):
    p=[0.]*225
    for i in range(15):p[i*15+i]=.1
    return {'last_measurement_ns':t,'state':[0.]*15,'covariance':p}

class CompareTests(unittest.TestCase):
    def test_identity_does_not_certify_fidelity(self):
        r=compare_ekf([row()],[row()]);self.assertTrue(r['equivalent']);self.assertFalse(r['fidelity_verified'])
    def test_position_gate(self):
        a=row();b=row();b['state'][0]=.011;self.assertFalse(compare_ekf([a],[b])['equivalent'])
    def test_yaw_wrap(self):
        a=row();b=row();a['state'][5]=math.pi-.001;b['state'][5]=-math.pi+.001
        self.assertTrue(compare_ekf([a],[b])['equivalent'])
    def test_covariance_normalization(self):
        a=row();b=row();b['covariance']=[v*1.02 for v in b['covariance']]
        self.assertAlmostEqual(compare_ekf([a],[b])['covariance_relative_max'],.02)
    def test_missing_and_pairing(self):
        for rows in ([],[row(4000000)],[row(),row()]):
            with self.assertRaises(ValueError):compare_ekf([row()],rows)
    def test_invalid_covariance(self):
        b=row();b['covariance'][1]=1
        with self.assertRaises(ValueError):compare_ekf([row()],[b])
    def test_tf_error_fails(self):
        self.assertFalse(compare_ekf([row()],[row()],tf_errors=1)['equivalent'])
    def test_stochastic_summaries_not_fidelity(self):
        rows=[{k:0. for k in AMCL_MARGINS} for _ in range(20)]
        r=compare_amcl(rows,rows);self.assertTrue(r['summary_equivalent']);self.assertFalse(r['fidelity_verified'])
    def test_stochastic_insufficient_or_changed(self):
        rows=[{k:0. for k in AMCL_MARGINS} for _ in range(20)]
        with self.assertRaises(ValueError):compare_amcl(rows[:19],rows)
        other=copy.deepcopy(rows)
        for r in other:r['max_jump_m']=1.
        self.assertFalse(compare_amcl(rows,other)['summary_equivalent'])

if __name__=='__main__':unittest.main()
