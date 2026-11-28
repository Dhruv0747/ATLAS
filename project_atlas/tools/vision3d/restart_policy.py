"""Durable web-only restart budget and policy restoration.

Caller must hold an exclusive transaction lock. No effects on import. Generic
unit name supports native fake-unit tests; production caller must pin the web unit.
"""
import json
import os
from pathlib import Path
import subprocess


def save(path,data):
    tmp=path.with_suffix('.tmp')
    with tmp.open('w') as f:json.dump(data,f);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
    fd=os.open(path.parent,os.O_DIRECTORY);os.fsync(fd);os.close(fd)


class Policy:
    def __init__(self,root,unit,unit_root,user=True):
        self.root=Path(root);self.unit=unit;self.user=user
        self.path=Path(unit_root)/(unit+'.d')/'99-atlas-bounded-restart.conf'
        self.state=self.root/'restart-policy.json'
    def command(self,*args):
        return subprocess.check_output(['systemctl',*(['--user'] if self.user else []),*args],text=True,timeout=15).strip()
    def prop(self,key):return self.command('show',self.unit,'-p',key,'--value')
    def load(self):return json.loads(self.state.read_text())
    def prepare(self):
        if self.state.exists() or self.path.exists():raise ValueError('transaction/policy already exists')
        if self.prop('Job') not in ('','0'):raise ValueError('existing systemd job')
        state={'unit':self.unit,'original_restart':self.prop('Restart'),'original_pid':self.prop('MainPID'),'activation':False,'rollback':False,'restored':False}
        # Save intent BEFORE modifying systemd. Recovery handles every later boundary.
        save(self.state,state);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.path.open('x') as f:f.write('[Service]\nRestart=no\n');f.flush();os.fsync(f.fileno())
        self.command('daemon-reload')
        if self.prop('Restart')!='no':raise ValueError('Restart=no not effective')
    def restart(self,phase):
        if phase not in ('activation','rollback'):raise ValueError('invalid phase')
        state=self.load()
        if state['restored'] or state[phase] or (phase=='activation' and state['rollback']):raise ValueError('restart budget consumed')
        if self.prop('Restart')!='no' or self.prop('Job') not in ('','0'):raise ValueError('restart policy/job unsafe')
        state[phase]=True;save(self.state,state)  # reservation survives kill before command
        self.command('restart',self.unit)
    def stop_and_quiesce(self):
        # Explicit stop cancels pending start/restart jobs; never overlaps recovery start.
        self.command('stop',self.unit)
        if self.prop('Job') not in ('','0') or self.prop('MainPID')!='0' or self.prop('ActiveState') not in ('inactive','failed'):
            raise ValueError('web not quiescent; no recovery start allowed')
    def restore(self):
        state=self.load()
        if state['restored']:
            if self.prop('Restart')!=state['original_restart']:raise ValueError('restored policy drift')
            return
        # Failed recovery: restore policy ONLY after explicit stop. Restoring always
        # on an inactive, deliberately stopped unit does not start it.
        self.stop_and_quiesce()
        if self.path.exists():
            if self.path.is_symlink() or self.path.read_text()!='[Service]\nRestart=no\n':raise ValueError('policy ownership mismatch')
            self.path.unlink()
        self.command('daemon-reload')
        if self.prop('Restart')!=state['original_restart'] or self.prop('MainPID')!='0':raise ValueError('policy restore failed')
        state['restored']=True;save(self.state,state)
    def restore_healthy(self):
        state=self.load()
        if self.prop('ActiveState')!='active' or self.prop('Restart')!='no':raise ValueError('web not healthy/controlled')
        if self.path.is_symlink() or self.path.read_text()!='[Service]\nRestart=no\n':raise ValueError('policy ownership mismatch')
        self.path.unlink();self.command('daemon-reload')
        if self.prop('Restart')!=state['original_restart']:raise ValueError('policy restore mismatch')
        state['restored']=True;save(self.state,state)
    def restore_untouched(self):
        state=self.load()
        if state['activation'] or self.prop('MainPID')!=state['original_pid'] or self.prop('ActiveState')!='active':raise ValueError('original process identity changed')
        if self.path.exists():
            if self.path.is_symlink() or self.path.read_text()!='[Service]\nRestart=no\n':raise ValueError('override changed')
            self.path.unlink()
        self.command('daemon-reload')
        if self.prop('Restart')!=state['original_restart'] or self.prop('MainPID')!=state['original_pid']:raise ValueError('untouched restoration failed')
        state['restored']=True;save(self.state,state)
