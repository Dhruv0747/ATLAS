import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]/'tools/diagnostics'
spec=importlib.util.spec_from_file_location('voice_profile',ROOT/'voice_cpu_once.py')
V=importlib.util.module_from_spec(spec);spec.loader.exec_module(V)

class VoiceProfileTests(unittest.TestCase):
    def module(self): return V.configure(V.load_helper(ROOT/'native_dashboard_cpu_once.py'))

    def test_exact_voice_target_and_hashes(self):
        m=self.module()
        self.assertEqual(m.TARGET_UNIT,'atlas-voice-companion.service')
        self.assertEqual(m.TARGET_SCRIPT,'scripts/atlas_voice_companion.py')
        self.assertEqual(m.HASHES[m.TARGET_SCRIPT],V.VOICE_SHA)
        self.assertEqual(len(m.HASHES),7)
        self.assertEqual(m.STAGE,V.STAGE)

    def test_other_arguments_rejected(self):
        for arg in ('--ignore-everything','--pid','--native'):
            with patch.object(V.sys,'argv',['voice',arg]), self.assertRaises(SystemExit):
                V.main()

    def test_entry_forces_gil_without_exception(self):
        m=self.module()
        with patch.object(V.sys,'argv',['voice']),patch.object(V,'load_helper',return_value=m),patch.object(m,'main',return_value=0) as main:
            self.assertEqual(V.main(),0)
            self.assertEqual(m.parse_options(V.sys.argv[1:]),(True,False))
            main.assert_called_once()

    def test_owner_cpu_exception_only(self):
        m=self.module()
        with patch.object(V.sys,'argv',['voice','--diagnostic-cpu-report-only']),patch.object(V,'load_helper',return_value=m),patch.object(m,'main',return_value=0):
            self.assertEqual(V.main(),0)
            self.assertEqual(m.parse_options(V.sys.argv[1:]),(True,True))
            with self.assertRaises(RuntimeError):m.checked_cpu(float('nan'),True)

    def test_no_audio_locals_or_subprocess_capture(self):
        command=self.module().python_command(2021,Path('/tmp/profile.json'))
        self.assertEqual(command[command.index('--duration')+1],'10')
        self.assertEqual(command[command.index('--rate')+1],'20')
        for flag in ('--locals','--subprocesses','--idle'):
            self.assertNotIn(flag,command)
        self.assertIn('--nonblocking',command)
        self.assertIn('--threads',command)

    def test_one_stable_hot_thread_suffices(self):
        m=self.module()
        self.assertEqual(m.select_hot_threads({'2':{'birth':3,'ticks':4}},
            {'2':{'birth':3,'ticks':8}},count=1),{'2':3})

    def test_tampered_helper_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bad.py';p.write_text('raise AssertionError()')
            with self.assertRaisesRegex(RuntimeError,'hash mismatch'):V.load_helper(p)

if __name__=='__main__': unittest.main()
