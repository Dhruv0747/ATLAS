from pathlib import Path
import tempfile
import unittest
from stage20_package_manifest import prepare
class ManifestTests(unittest.TestCase):
    def test_hashes_actual_files_and_cannot_enable(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'binary';p.write_bytes(b'actual')
            m=prepare([p],{'config':'preserved'},'source')
            self.assertFalse(m['deployment_ready']);self.assertFalse(m['installed'])
            self.assertEqual(len(m['binary_files'][str(p)]),64)
            self.assertFalse(m['restart_now'])
if __name__=='__main__':unittest.main()
