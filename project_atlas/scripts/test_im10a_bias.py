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

    def test_no_ekf_imu_input_enabled(self):
        import re
        config=Path(__file__).parents[1]/'config'/'atlas_ekf.yaml'
        self.assertIsNone(re.search(r'^\s*imu\d+\s*:',config.read_text(),re.M))

    def test_zero_at_bias(self):
        self.assertEqual(ns['corrected_gyro']([.01,.02,.03],[.01,.02,.03]),(0.,0.,0.))
    def test_mount_rotation(self):
        self.assertEqual(ns['corrected_gyro']([1.,2.,3.],[0.,0.,0.]),(-1.,-2.,3.))
if __name__=='__main__':unittest.main()
