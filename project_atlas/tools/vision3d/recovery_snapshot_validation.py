"""Offline-tested validation/budget primitives; no service operations or CLI.
Independent HTTP/resource observations are supplied by the bounded supervisor.
This module never launches a producer, ROS node or systemctl command.
"""
import json
from pathlib import Path
from restart_policy import save
from existing_safety_snapshot import Consumer

UNIT='atlas-sensor-recovery.service'
OVERRIDE='[Service]\nRestart=no\nEnvironment=ATLAS_RESTART_SNAPSHOT=1\n'

class Validation:
    def __init__(self, state_path, snapshot, boot_id):
        self.path=Path(state_path)
        self.consumer=Consumer(snapshot,boot_id)
        self.failure=None
        self.ready=False
        self.started=None
        self.last_independent=None
        self.last_published=None
        self.updates=0

    def independent(self, now, observation):
        # Only accepted after the caller's strict HTTP/resource validation.
        if observation.get('estop') is not True or observation.get('stationary') is not True:
            self.fail('independent safety rejected')
        if not (0<=observation['cpu']<75 and 0<=observation['ram']<80 and 0<observation['temp']<70):
            self.fail('resource admission rejected')
        self.last_independent=now

    def fail(self, reason):
        self.failure=self.failure or reason
        raise ValueError(self.failure)

    def check_independent(self, now):
        if self.failure:self.fail(self.failure)
        if self.last_independent is None or not 0<=now-self.last_independent<=1.5:
            self.fail('independent safety missing/stalled')

    def reserve_restart(self, phase, now):
        self.check_independent(now)
        if phase not in ('activation','rollback'):self.fail('unknown restart phase')
        state=json.loads(self.path.read_text()) if self.path.exists() else {'unit':UNIT,'activation':False,'rollback':False}
        if state['unit']!=UNIT or state[phase] or (phase=='activation' and state['rollback']):self.fail('restart budget exhausted')
        state[phase]=True
        save(self.path,state)  # Reserve BEFORE any external restart request.
        if phase=='activation':self.started=now

    def snapshot_check(self, now):
        self.check_independent(now)
        if self.started is None:self.fail('activation not reserved')
        if now-self.started>40:self.fail('validation deadline')
        # During bounded initial callback fill, snapshot is NOT used as safety.
        # Once admitted, every rejection latches via Consumer and this session.
        try:
            if not self.ready:
                from existing_safety_snapshot import verify
                result=verify(self.consumer.path,now,self.consumer.boot_id)
            else:result=self.consumer.check(now)
        except Exception as exc:
            if self.ready or now-self.started>=5:self.fail('snapshot rejected: '+str(exc))
            return {'ready':False,'reason':str(exc)}
        self.ready=True
        # Read-only progress evidence; exact safety check above uses its own
        # atomic file read. Progress is not a replacement for freshness checks.
        try:stamp=json.loads(Path(self.consumer.path).read_text())['published_mono']
        except Exception as exc:self.fail('snapshot progress unavailable: '+str(exc))
        if self.last_published is not None and stamp<self.last_published:self.fail('snapshot timestamp regression')
        if stamp!=self.last_published:self.updates+=1
        self.last_published=stamp
        return {'ready':True,'safety':result,'updates':self.updates}
