"""Native offline fixtures using the original private archive, never deployed paths."""
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest

from mux_publisher_files import MuxFiles, ARCHIVE, MUX, HELPER, Conflict


@unittest.skipUnless(os.environ.get('ATLAS_MUX_TEST_ARCHIVE'), 'private reviewed fixture not supplied')
class MuxFilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.stage, self.tx, self.live = (root / p for p in ('mux', 'tx', 'scripts'))
        for directory in (self.stage, self.tx, self.live):
            directory.mkdir(mode=0o700)
        archive = root / ARCHIVE
        shutil.copyfile(os.environ['ATLAS_MUX_TEST_ARCHIVE'], archive)
        with tarfile.open(archive) as bundle:
            for entry in bundle:
                self.assertTrue(entry.isfile() and not Path(entry.name).is_absolute() and '..' not in Path(entry.name).parts)
                target = self.stage / entry.name
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(bundle.extractfile(entry).read());target.chmod(0o644)
        self.files = MuxFiles(self.stage, self.tx, self.live)
        self.original = self.live / MUX
        self.original.write_bytes((self.stage/'rollback'/MUX).read_bytes())
        self.original.chmod(0o755)
        stamp = self.files.binding['files'][MUX]['mtime_ns']
        os.utime(self.original, ns=(stamp, stamp))
        self.check = lambda: None

    def test_install_and_reconstructed_exact_rollback(self):
        self.files.install(self.check)
        self.files.verify_installed(self.check)
        restored = MuxFiles(self.stage, self.tx, self.live)
        restored.rollback(self.check)
        restored.verify_original(self.check)
        self.assertFalse((self.live / HELPER).exists())
        restored.rollback(self.check)
        with self.assertRaises(Conflict):restored.install(self.check)

    def test_interrupted_after_helper_does_not_install_mux(self):
        def interrupt():
            if (self.live / HELPER).exists():raise TimeoutError('worker budget')
        with self.assertRaises(TimeoutError):self.files.install(interrupt)
        self.assertEqual(self.original.read_bytes(),(self.stage/'rollback'/MUX).read_bytes())
        MuxFiles(self.stage,self.tx,self.live).rollback(self.check)
        self.files.verify_original(self.check)

    def test_lookalike_replacement_helper_is_never_removed(self):
        self.files.install(self.check)
        helper=self.live / HELPER
        replacement=self.live/'unexpected';shutil.copy2(helper,replacement);os.replace(replacement,helper)
        with self.assertRaises(Conflict):self.files.rollback(self.check)
        self.assertTrue(helper.exists())

    def test_metadata_or_symlink_drift_rejected_before_live_mutation(self):
        self.original.chmod(0o644)
        with self.assertRaises(Conflict):self.files.install(self.check)
        self.assertFalse((self.live/HELPER).exists())
        self.original.chmod(0o755)
        (self.live/HELPER).symlink_to('missing')
        with self.assertRaises(Conflict):self.files.verify_original(self.check)

    def test_expired_guard_blocks_rollback_mutations(self):
        self.files.install(self.check)
        def expired():raise TimeoutError('cleanup budget')
        with self.assertRaises(TimeoutError):self.files.rollback(expired)
        self.files.verify_installed(self.check)

    def test_rollback_does_not_require_surviving_stage(self):
        self.files.install(self.check)
        shutil.rmtree(self.stage)
        self.files.rollback(self.check)
        self.assertFalse((self.live/HELPER).exists())
        self.assertEqual(self.original.stat().st_mtime_ns,1793339497617618223)

    def test_backup_metadata_drift_never_replaces_live_file(self):
        self.files.install(self.check)
        (self.tx / "mux-files" / "backup").chmod(0o600)
        installed=self.original.stat().st_ino
        with self.assertRaises(Conflict):self.files.rollback(self.check)
        self.assertEqual(self.original.stat().st_ino,installed)

    def test_installed_helper_permission_drift_is_rejected(self):
        self.files.install(self.check)
        (self.live/HELPER).chmod(0o600)
        with self.assertRaises(Conflict):self.files.verify_installed(self.check)

    def test_missing_intent_is_not_a_successful_rollback_after_mutation(self):
        self.files.install(self.check)
        self.files.intent.unlink()
        with self.assertRaises(Conflict):self.files.rollback(self.check)
        self.assertTrue((self.live/HELPER).exists())
