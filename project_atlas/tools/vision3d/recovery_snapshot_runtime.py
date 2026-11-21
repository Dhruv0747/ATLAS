"""Bounded recovery-only runtime transaction. No actions on import.
Production invocation must be separately approved and owned by a systemd unit
with ExecStopPost=... --cleanup, Restart=no and RuntimeMaxSec=90.
"""
import json
import os
from pathlib import Path
import subprocess
import time
from restart_policy import save

UNIT='atlas-sensor-recovery.service'
TEXT='[Service]\nRestart=no\nEnvironment=ATLAS_RESTART_SNAPSHOT=1\n'

class Transaction:
    def __init__(self, root, unit=UNIT, unit_root='/run/user/1000/systemd/user', user=True, check=lambda:None):
        self.root=Path(root);self.unit=unit;self.user=user;self.check=check
        self.override=Path(unit_root)/(unit+'.d')/'99-atlas-snapshot-runtime.conf'
        self.state=self.root/'transaction.json'

    def command(self,*args,guard=True,timeout=3):
        # systemctl jobs are always nonblocking; polling safety never waits for a
        # restart timeout. A stuck systemctl client is independently killed.
        proc=subprocess.Popen(['systemctl',*(['--user'] if self.user else []),*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        deadline=time.monotonic()+timeout
        try:
            while proc.poll() is None:
                if guard:self.check()
                if time.monotonic()>=deadline:raise TimeoutError('systemctl client deadline')
                time.sleep(.05)
            out,err=proc.communicate()
            if proc.returncode:raise RuntimeError(err.strip())
            return out.strip()
        finally:
            if proc.poll() is None:proc.kill();proc.wait(timeout=1)
            if proc.stdout:proc.stdout.close()
            if proc.stderr:proc.stderr.close()

    def prop(self,key,guard=True):return self.command('show',self.unit,'-p',key,'--value',guard=guard)
    def load(self):return json.loads(self.state.read_text())
    def prepare(self):
        self.check()
        if self.state.exists() or self.override.exists():raise ValueError('transaction already used')
        if self.prop('Job') not in ('','0') or self.prop('ActiveState')!='active':raise ValueError('service not quiescent/active')
        state={'unit':self.unit,'original_restart':self.prop('Restart'),'pid':self.prop('MainPID'),'activation':False,'rollback':False,'restored':False}
        save(self.state,state)
        self.override.parent.mkdir(parents=True,exist_ok=True)
        # Atomic complete drop-in; intent above supports cleanup at every boundary.
        save(self.root/'override-intent.json',{'path':str(self.override),'text':TEXT})
        temp=self.override.with_suffix('.tmp')
        with temp.open('x') as f:f.write(TEXT);f.flush();os.fsync(f.fileno())
        os.replace(temp,self.override)
        self.command('daemon-reload')
        if self.prop('Restart')!='no':raise ValueError('restart bound not effective')

    def restart(self,phase):
        self.check();state=self.load()
        if phase not in ('activation','rollback') or state['restored'] or state[phase] or (phase=='activation' and state['rollback']):raise ValueError('restart budget exhausted')
        if self.prop('Restart')!='no' or self.prop('Job') not in ('','0'):raise ValueError('unbounded/pending restart')
        state[phase]=True;save(self.state,state)
        self.command('--no-block','restart',self.unit)
        deadline=time.monotonic()+8
        while True:
            self.check()
            if time.monotonic()>deadline:raise TimeoutError('restart job deadline')
            active=self.prop('ActiveState');job=self.prop('Job')
            if active=='active' and job in ('','0') and self.prop('MainPID')!='0':return
            if active=='failed':raise ValueError('service failed')
            time.sleep(.1)

    def remove_optin(self):
        # Keep Restart=no for the one controlled restoration restart.
        if self.override.read_text()!=TEXT:raise ValueError('override ownership')
        temp=self.override.with_suffix('.tmp')
        with temp.open('x') as f:f.write('[Service]\nRestart=no\n');f.flush();os.fsync(f.fileno())
        os.replace(temp,self.override);self.command('daemon-reload')

    def cleanup(self):
        # Independent ExecStopPost path: never starts/restarts any service.
        if not self.state.exists():return
        state=self.load()
        if state['unit']!=self.unit:raise ValueError('cleanup unit mismatch')
        if state['restored']:return
        untouched=not state['activation'] and self.prop('MainPID',False)==state['pid'] and self.prop('ActiveState',False)=='active'
        if not untouched:
            self.command('--no-block','stop',self.unit,guard=False)
            deadline=time.monotonic()+10
            while self.prop('MainPID',False)!='0' or self.prop('Job',False) not in ('','0'):
                if time.monotonic()>deadline:raise TimeoutError('cleanup cannot quiesce; retain Restart=no')
                time.sleep(.1)
        for path in (self.override,self.override.with_suffix('.tmp')):
            if path.exists():
                if path.is_symlink() or path.read_text() not in (TEXT,'[Service]\nRestart=no\n'):raise ValueError('cleanup ownership mismatch')
                path.unlink()
        self.command('daemon-reload',guard=False)
        if self.prop('Restart',False)!=state['original_restart']:raise ValueError('original policy not restored')
        state['restored']=True;save(self.state,state)
        save(self.root/'cleanup.json',{'policy':'RESTORED','web_untouched':True,'recovery':'ORIGINAL_PID' if untouched else 'STOPPED','restart_attempts':int(state['activation'])+int(state['rollback'])})

    def finish(self):
        self.check();state=self.load()
        if not state['rollback'] or self.prop('ActiveState')!='active':raise ValueError('restoration not validated')
        if self.override.read_text()!='[Service]\nRestart=no\n':raise ValueError('opt-in still present')
        self.override.unlink();self.command('daemon-reload')
        if self.prop('Restart')!=state['original_restart']:raise ValueError('policy mismatch')
        state['restored']=True;save(self.state,state)
