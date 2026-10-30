"""Local mapping sessions, bounded storage and interruption quarantine."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time
import uuid


def atomic(path, value):
    path=Path(path); tmp=path.with_suffix('.tmp')
    with tmp.open('w') as f:
        json.dump(value,f,allow_nan=False);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
    fd=os.open(str(path.parent),os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def usage(path):
    return sum(p.stat().st_size for p in Path(path).rglob('*') if p.is_file())


def budget(path, maximum=2*1024**3, reserve=1024**3):
    if usage(path)>=maximum:raise ValueError('mapping storage budget reached')
    if shutil.disk_usage(path).free<reserve:raise ValueError('free storage reserve reached')


def integrity(path):
    if not Path(path).is_file():raise ValueError('mapping database missing')
    with sqlite3.connect('file:'+str(Path(path).resolve())+'?mode=ro',uri=True,timeout=1) as db:
        if db.execute('pragma integrity_check').fetchall()!=[('ok',)]:
            raise ValueError('database integrity rejected')
        return db.execute('select count(*) from Node').fetchone()[0]


def new_session(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    budget(root,8*1024**3,1024**3)  # retained sessions: refuse new work, never delete maps
    path=root/(time.strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8])
    path.mkdir();budget(path)
    atomic(path/'status.json',dict(state='STARTING',created=time.time(),label='CALIBRATION VALIDATION REQUIRED'))
    return path


def finalize(path, reason):
    path=Path(path);result=dict(state='QUARANTINED',reason=reason,ended=time.time())
    try:
        result['nodes']=integrity(path/'map.db')
        h=hashlib.sha256()
        with (path/'map.db').open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
        result.update(state='CLOSED',database_sha256=h.hexdigest())
    except Exception as e:result['integrity_error']=str(e)
    atomic(path/'status.json',result)
    return result


def recover(root):
    """Mark interrupted sessions; never open a DB that may need journal recovery.

    Original DB/journal retained. Explicit offline copy/recovery is required.
    """
    for p in Path(root).glob('*/status.json'):
        try:
            data=json.loads(p.read_text())
            if data.get('state') in ('STARTING','RUNNING'):
                atomic(p,dict(state='QUARANTINED',reason='interrupted session; preserve DB and journals; no auto resume'))
        except (ValueError,OSError):continue
