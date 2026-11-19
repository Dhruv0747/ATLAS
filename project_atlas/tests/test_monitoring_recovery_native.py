"""Opt-in PC/WSL native systemd lifecycle tests; ONLY uniquely named fake units."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

import pytest

pytestmark=pytest.mark.skipif(os.environ.get('ATLAS_FAKE_SYSTEMD')!='1',reason='explicit isolated PC native test only')


def run(*args, check=True):
    return subprocess.run(['sudo','-n',*args],capture_output=True,text=True,check=check,timeout=15)


@pytest.mark.parametrize('cause',['timeout','sigkill','cleanup-killed','main-and-cleanup-stuck'])
def test_systemd_cleanup_and_independent_expiry(cause):
    unit='atlas-offline-test-'+uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix='atlas-offline-') as temp:
        path=Path(temp); marker=path/'cleanup'; fallback=path/'expiry'
        stuck=cause=='main-and-cleanup-stuck'
        (path/'worker.py').write_text('import time,signal\n'+
            ('signal.signal(signal.SIGTERM,signal.SIG_IGN)\n' if stuck else '')+'time.sleep(30)\n')
        (path/'cleanup.py').write_text(
            'from pathlib import Path\nimport os,time\n'
            f'Path({str(marker)!r}).write_text(os.environ.get("SERVICE_RESULT","unknown"))\n'
            + ('time.sleep(30)\n' if cause=='cleanup-killed' or stuck else ''))
        (path/'fallback.py').write_text(f'from pathlib import Path\nPath({str(fallback)!r}).write_text("cleanup fallback ran")\n')
        try:
            if cause=='cleanup-killed' or stuck:
                run('systemd-run','--unit='+unit+'-expiry','--on-active=5s','--timer-property=AccuracySec=100ms',
                    '--property=Type=oneshot','--property=Restart=no','--property=TimeoutStartSec=3',
                    '/usr/bin/python3',str(path/'fallback.py'))
            run('systemd-run','--unit='+unit,'--property=Type=exec','--property=Restart=no',
                '--property=RuntimeMaxSec=2','--property=TimeoutStopSec=1','--property=KillMode=control-group',
                '--property=ExecStopPost=/usr/bin/python3 '+str(path/'cleanup.py'),
                '/usr/bin/python3',str(path/'worker.py'))
            if cause=='sigkill':
                run('systemctl','kill','--kill-who=main','--signal=KILL',unit+'.service')
            end=time.monotonic()+9
            while time.monotonic()<end:
                if marker.exists() and (cause not in ('cleanup-killed','main-and-cleanup-stuck') or fallback.exists()): break
                time.sleep(.1)
            assert marker.exists(), 'ExecStopPost did not run'
            assert marker.read_text() in ('timeout','signal')
            if cause=='cleanup-killed' or stuck:
                assert fallback.exists(), 'independent fallback did not run'
                assert run('systemctl','show',unit+'.service','-p','ControlPID','--value').stdout.strip()=='0'
            assert run('systemctl','show',unit+'.service','-p','NRestarts','--value').stdout.strip()=='0'
        finally:
            # Only our random fake names; never ATLAS production/monitoring units.
            run('systemctl','stop',unit+'.service',check=False)
            if cause=='cleanup-killed' or stuck:
                run('systemctl','stop',unit+'-expiry.timer',unit+'-expiry.service',check=False)
            run('systemctl','reset-failed',unit+'.service',check=False)
