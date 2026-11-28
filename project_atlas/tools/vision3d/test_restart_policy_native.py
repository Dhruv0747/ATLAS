"""PC WSL native systemd only; refuses Jetson and only uses a unique fake unit."""
import os
import platform
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from restart_policy import Policy


@unittest.skipUnless('microsoft' in platform.release().lower() and os.geteuid()==0,'WSL root fake units only')
class NativePolicyTests(unittest.TestCase):
    def test_bounded_restart_restore_and_interruption(self):
        name='atlas-offline-restart-test-'+str(os.getpid())+'.service'
        unit=Path('/run/systemd/system')/name
        def cmd(*args):return subprocess.check_output(['systemctl',*args],text=True).strip()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);unit.write_text('[Service]\nType=simple\nExecStart=/usr/bin/sleep infinity\nRestart=always\nRestartSec=0.1\n')
            try:
                cmd('daemon-reload');cmd('start',name)
                p=Policy(root,name,'/run/systemd/system',user=False);p.prepare()
                self.assertEqual(p.prop('Restart'),'no')
                p.restart('activation');pid=p.prop('MainPID')
                with self.assertRaises(ValueError):p.restart('activation')
                p.restart('rollback');self.assertNotEqual(pid,p.prop('MainPID'))
                with self.assertRaises(ValueError):p.restart('rollback')
                # Simulate supervisor interruption: new recovery instance uses disk state.
                recovery=Policy(root,name,'/run/systemd/system',user=False)
                recovery.restore();self.assertEqual(recovery.prop('Restart'),'always')
                time.sleep(.4);self.assertEqual(recovery.prop('MainPID'),'0')
                recovery.restore();self.assertEqual(recovery.prop('MainPID'),'0')
            finally:
                cmd('stop',name)
                if p.path.exists():p.path.unlink()
                unit.unlink();cmd('daemon-reload')

if __name__=='__main__':unittest.main()
