"""Offline adapter candidate for an EXISTING ROS subscriber's observations.

No ROS imports, subscribers, threads or background loop. Not integrated/deployed.
Producer exports raw receipt times; consumer applies the same stationary gates.
"""
import json
import os
from pathlib import Path
from restart_safety_observer import Safety


def publish(path,values,now,boot_id):
    # Caller supplies existing callback values/timestamps. Never refresh their age.
    payload={'boot_id':boot_id,'published_mono':now,'observations':values}
    raw=json.dumps(payload,allow_nan=False,separators=(',',':')).encode()
    if len(raw)>16384:raise ValueError('safety snapshot too large')
    path=Path(path);temp=path.with_suffix('.tmp')
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush()
    os.replace(temp,path)


def verify(path,now,boot_id):
    with Path(path).open('rb') as f:raw=f.read(16385)
    if len(raw)>16384:raise ValueError('oversized snapshot')
    data=json.loads(raw)
    if data['boot_id']!=boot_id or not 0<=now-data['published_mono']<=.75:raise ValueError('wrong boot/stale producer')
    state=Safety()
    for key,item in data['observations'].items():
        if key not in ('policy','command','encoders') or len(item)!=2:raise ValueError('invalid observation')
        state.receive(key,item[0],item[1])
    result=state.evaluate(now)
    if not result['safe']:raise ValueError(result['reason'])
    return result


class Producer:
    """Opt-in export from existing callbacks; no ROS entity or background task."""
    def __init__(self, path, boot_id):
        self.path = Path(path)
        self.boot_id = boot_id
        self.values = {}
        self.last_write = float('-inf')
        self.failed = False

    def receive(self, key, value, now):
        if self.failed:
            return
        self.values[key] = [value, now]
        if now - self.last_write < .1:
            return
        try:
            publish(self.path, self.values, now, self.boot_id)
            self.last_write = now
        except Exception:
            # Never disturb recovery callbacks; stale cache rejects the consumer.
            self.failed = True
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass


class Consumer:
    """Session-latched rejection, including failures before admission."""
    def __init__(self, path, boot_id):
        import threading
        self.path, self.boot_id = path, boot_id
        self.failure = None
        self.lock = threading.Lock()

    def check(self, now):
        with self.lock:
            if self.failure is not None:
                raise ValueError(self.failure)
            try:
                return verify(self.path, now, self.boot_id)
            except Exception as exc:
                self.failure = str(exc)
                raise
