import hashlib
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/vision3d'))
import prepare_feature_ui as ui


class FeatureUiTests(unittest.TestCase):
    def test_unknown_baseline_rejected(self):
        with self.assertRaises(ValueError):ui.patch(b'<main></main>')
    def test_static_only(self):
        block=ui.fragment().decode()
        self.assertEqual(block.count('<article '),6)
        self.assertEqual(block.count('class="btn" disabled'),24)
        for prohibited in ('<script','onclick','fetch(','src=','href=','/api/'):
            self.assertNotIn(prohibited,block)
        self.assertNotIn('>READY<',block)
    def test_changed_rollback_rejected(self):
        with self.assertRaises(ValueError):ui.inverse(ui.fragment()+b'changed original')


if __name__=='__main__':unittest.main()
