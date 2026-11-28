"""Offline admission/cleanup tests; no ROS participant or production access."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import offboard_native as target


class Guards(unittest.TestCase):
    def test_host_network_refused(self):
        with patch.dict(target.os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):target.isolation()

    def test_existing_lock_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            lock=Path(directory)/'.offboard-active';lock.write_text('existing evidence')
            with patch.object(target,'isolation'):
                with self.assertRaises(FileExistsError):target.Recorder(directory)
            self.assertEqual(lock.read_text(),'existing evidence')

    def test_disk_budget_refused_before_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(target,'isolation'), patch.object(target,'bytes_under',return_value=target.LIMIT), patch.object(target,'QueuedWriter') as worker:
                with self.assertRaises(OSError):target.Recorder(directory)
                worker.assert_not_called()
            self.assertFalse((Path(directory)/'.offboard-active').exists())

    def test_failed_shutdown_keeps_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(target,'isolation'), patch.object(target,'QueuedWriter') as factory:
                worker=factory.return_value
                worker.wait_idle.return_value=False
                worker.shutdown.return_value=False
                with self.assertRaises(RuntimeError):target.Recorder(directory)
            self.assertTrue((Path(directory)/'.offboard-active').exists())


if __name__=='__main__':unittest.main()
