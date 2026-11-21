import tempfile
from pathlib import Path
import unittest
from offboard_storage_probe import StorageProbe, validate


class ProbeTests(unittest.TestCase):
    def test_partial_cancel_preserves_payload(self):
        with tempfile.TemporaryDirectory() as td:
            sink=StorageProbe(Path(td)/'bag',{'/yahboom/encoder/m1':'std_msgs/msg/Int32'})
            raw=b'\x00\x01\x00\x00\x7b\x00\x00\x00'
            sink.write('/yahboom/encoder/m1',raw,100)
            sink.close();sink.close()
            self.assertEqual(validate(sink.path),1)
            with self.assertRaises(ValueError):sink.write('/yahboom/encoder/m1',raw,101)

    def test_no_overwrite_or_unlisted_topic(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):StorageProbe(td,{})
            with self.assertRaises(ValueError):StorageProbe(Path(td)/'bad',{'/bad':'std_msgs/msg/Int32'})

    def test_quota_preserves_partial(self):
        with tempfile.TemporaryDirectory() as td:
            sink=StorageProbe(Path(td)/'bag',{'/yahboom/encoder/m1':'std_msgs/msg/Int32'},quota=1024**2)
            try:
                with self.assertRaises(RuntimeError):
                    sink.write('/yahboom/encoder/m1',bytes(1024**2),100)
            finally:sink.close()
            self.assertTrue(sink.path.exists())


if __name__=='__main__':unittest.main()
