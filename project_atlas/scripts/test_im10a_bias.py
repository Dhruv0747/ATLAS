"""Pure arithmetic test, no sensor or ROS connection."""
import ast
from pathlib import Path
import unittest
tree=ast.parse(Path(__file__).with_name('atlas_im10a_observer.py').read_text())
fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='corrected_gyro')
ns={}
exec(compile(ast.Module(body=[fn],type_ignores=[]),'<bias>','exec'),ns)
class BiasTests(unittest.TestCase):
    def test_orientation_excluded_on_both_imu_messages(self):
        source=Path(__file__).with_name('atlas_im10a_observer.py').read_text()
        self.assertIn('m.orientation_covariance[0] = -1.', source)
        self.assertIn('c.orientation_covariance[0] = -1.', source)
        self.assertIn("'magnetic_heading_used_for_navigation': False", source)

    def test_ekf_uses_only_corrected_yaw_rate(self):
        config=Path(__file__).parents[1]/'config'/'atlas_ekf.yaml'
        text=config.read_text()
        self.assertIn('imu0: /im10a/imu/bias_corrected_candidate', text)
        self.assertIn('false, false, true,\n                  false, false, false]', text)
        # Wheel pose-yaw and yaw-rate entries are intentionally both false.
        self.assertGreaterEqual(text.count('false, false, false,'), 4)

    def test_live_status_matches_commissioned_fusion(self):
        source=Path(__file__).with_name('atlas_im10a_observer.py').read_text()
        self.assertIn("'LIVE_FUSED_GYRO_Z'", source)
        self.assertIn("'EKF gyro-Z enabled'", source)
        self.assertNotIn('EKF disabled; magnetic heading', source)

    def test_candidate_requires_explicit_navigation_qualification(self):
        source=Path(__file__).with_name('atlas_im10a_observer.py').read_text()
        self.assertIn("config.get('navigation_qualified') is not True", source)
        self.assertIn('if self.fusion_enabled:', source)

    def test_zero_at_bias(self):
        self.assertEqual(ns['corrected_gyro']([.01,.02,.03],[.01,.02,.03]),(0.,0.,0.))
    def test_mount_rotation(self):
        self.assertEqual(ns['corrected_gyro']([1.,2.,3.],[0.,0.,0.]),(-1.,-2.,3.))
if __name__=='__main__':unittest.main()
