"""Offline build-supervisor failure paths; no SSH, ROS or subprocess activation."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/vision3d'))
import paced_build as B


class BuildTests(unittest.TestCase):
    def test_no_opt_in(self):
        with patch.object(sys,'argv',['build']), self.assertRaises(SystemExit):B.main()

    def test_existing_evidence_preserved(self):
        with tempfile.TemporaryDirectory() as d,patch.object(B,'STAGE',Path(d)),patch.object(sys,'argv',['build','--approve-isolated-build']):
            p=Path(d)/'stage28_paced_build.json';p.write_text('old')
            with self.assertRaises(SystemExit):B.main()
            self.assertEqual(p.read_text(),'old')

    def test_preflight_failure_never_launches(self):
        with tempfile.TemporaryDirectory() as d,patch.object(B,'STAGE',Path(d)),patch.object(sys,'argv',['build','--approve-isolated-build']),patch.object(B.gate,'preflight',side_effect=RuntimeError('unsafe')),patch.object(B.gate,'services',return_value={}),patch.object(B.subprocess,'Popen') as spawn:
            B.main();spawn.assert_not_called()
            r=json.loads((Path(d)/'stage28_paced_build.json').read_text())
            self.assertFalse(r['started']);self.assertEqual(r['failure'],'unsafe')

    def test_resource_failure_terminates_only_owned_child(self):
        with tempfile.TemporaryDirectory() as d,patch.object(B,'STAGE',Path(d)),patch.object(sys,'argv',['build','--approve-isolated-build']),patch.object(B.gate,'preflight',return_value=([],{})),patch.object(B.gate,'services',return_value={}),patch.object(B.gate,'ticks',return_value=(10,2)),patch.object(B.gate,'cpu_delta',return_value=81),patch.object(B.gate,'check',side_effect=B.gate.AdmissionError('CPU limit',{'cpu':81})),patch.object(B.time,'sleep'),patch.object(B.subprocess,'Popen') as spawn,patch.object(B,'OwnedPacer') as pacer,patch.object(B.os,'killpg') as kill:
            proc=Mock(pid=12345);proc.poll.return_value=None;spawn.return_value=proc
            pacer.return_value.start.return_value.error=None
            B.main()
            kill.assert_called_once_with(12345,B.signal.SIGTERM)
            r=json.loads((Path(d)/'stage28_paced_build.json').read_text())
            self.assertEqual(r['result'],'BLOCKED');self.assertEqual(r['failed_sample']['cpu'],81)
            pacer.return_value.start.return_value.close.assert_called_once()
