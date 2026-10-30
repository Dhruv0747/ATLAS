"""Real SIGKILL/ExecStopPost recovery of fake WSL services and fixture files only."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import time
import unittest


@unittest.skipUnless('microsoft' in platform.release().lower() and os.geteuid()==0,'WSL only')
class CrashTests(unittest.TestCase):
    def test_kill_recovers_files_and_policy_without_start_loop(self):
        helpers=str(Path(__file__).resolve().parent)
        for phase in ('policy','files','activation','policy_restored'):
            with self.subTest(phase=phase),tempfile.TemporaryDirectory() as d:
                root=Path(d);stage=root/'stage';stage.mkdir();live=root/'live';live.mkdir();(stage/'backup').mkdir()
                (live/'app.py').write_bytes(b'original');(stage/'backup/app.py').write_bytes(b'original')
                name=f'atlas-offline-crash-{os.getpid()}-{phase}.service';supervisor='supervisor-'+name
                unit=Path('/run/systemd/system')/name;outer=unit.with_name(supervisor)
                def cmd(*args):return subprocess.check_output(['systemctl',*args],text=True).strip()
                prefix=f"import sys,os,signal;from pathlib import Path;sys.path.insert(0,{helpers!r});from restart_policy import Policy;import web_activation_supervisor as w;stage=Path({str(stage)!r});w.LIVE=Path({str(live)!r});w.policy=lambda _:Policy(stage,{name!r},'/run/systemd/system',user=False);p=w.policy(stage);"
                recovery=root/'recovery.py';recovery.write_text(prefix+"w.recover(stage);w.recover(stage);(stage/'done').write_text('recovered')")
                plan={'app.py':{'original':hashlib.sha256(b'original').hexdigest(),'candidate':hashlib.sha256(b'candidate').hexdigest()},'new.py':{'original':None,'candidate':hashlib.sha256(b'new').hexdigest()}}
                (stage/'installation-plan.json').write_text(json.dumps(plan))
                actions="p.prepare();"
                if phase!='policy':actions+="(w.LIVE/'app.py').write_bytes(b'candidate');(w.LIVE/'new.py').write_bytes(b'new');"
                if phase in ('activation','policy_restored'):actions+="p.restart('activation');"
                if phase=='policy_restored':actions+="p.restore_healthy();"
                driver=root/'driver.py';driver.write_text(prefix+actions+"os.kill(os.getpid(),signal.SIGKILL)")
                unit.write_text('[Service]\nExecStart=/usr/bin/sleep infinity\nRestart=always\nRestartSec=0.1\n')
                outer.write_text(f'[Service]\nExecStart=/usr/bin/python3 {driver}\nExecStopPost=/usr/bin/python3 {recovery}\nRestart=no\nTimeoutStopSec=15\n')
                try:
                    cmd('daemon-reload');cmd('start',name);cmd('start',supervisor)
                    deadline=time.monotonic()+8
                    while not (stage/'done').exists() and time.monotonic()<deadline:time.sleep(.1)
                    self.assertTrue((stage/'done').exists())
                    self.assertEqual((live/'app.py').read_bytes(),b'original');self.assertFalse((live/'new.py').exists())
                    self.assertEqual(cmd('show',name,'-p','Restart','--value'),'always')
                    time.sleep(.3)
                    if phase in ('activation','policy_restored'):self.assertEqual(cmd('show',name,'-p','MainPID','--value'),'0')
                    else:self.assertNotEqual(cmd('show',name,'-p','MainPID','--value'),'0')
                    state=json.loads((stage/'restart-policy.json').read_text());self.assertTrue(state['restored']);self.assertFalse(state['rollback'])
                finally:
                    subprocess.run(['systemctl','stop',supervisor,name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                    subprocess.run(['systemctl','reset-failed',supervisor],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                    unit.unlink(missing_ok=True);outer.unlink(missing_ok=True)
                    override=Path('/run/systemd/system')/(name+'.d')/'99-atlas-bounded-restart.conf';override.unlink(missing_ok=True)
                    cmd('daemon-reload')

if __name__=='__main__':unittest.main()
