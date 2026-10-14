"""Strict whole-file diagnostic capsule transaction and rollback rehearsal.

Complements the existing patch-package framework; never starts/enables/restarts
services. Production application needs a qualified manifest AND owner approval.
Historical diagnostic data is never a payload or rollback target.
"""
import json
from pathlib import Path
import shutil
import uuid
import time
from stage20_install_guard import check,sha

def target(root,relative):
    p=(root/relative).resolve()
    if not p.is_relative_to(root):raise ValueError('transaction path escape')
    return p

def atomic_copy(source,dest,expected):
    temp=dest.parent/('.stage20-'+uuid.uuid4().hex+'.tmp')
    with temp.open('xb'):pass
    try:
        shutil.copy2(source,temp)
        if sha(temp)!=expected:raise ValueError('staged checksum mismatch')
        temp.replace(dest)
    finally:
        if temp.exists():temp.unlink()  # Exact exclusively created staging file only.

def rollback(backup,root):
    root=Path(root).resolve();backup=Path(backup).resolve()
    if not backup.is_relative_to(root/'data/backups'):raise ValueError('wrong backup root')
    m=json.loads((backup/'transaction.json').read_text())
    # First validate every rollback target; never overwrite unrelated later edits.
    for f in m['files']:
        dest=target(root,f['path'])
        current=sha(dest) if dest.is_file() else None
        if current not in (f['before'],f['after']):raise ValueError('rollback refuses later live drift')
    for f in m['files']:
        dest=target(root,f['path'])
        original=target(backup/'originals',f['path'])
        if f['before'] is not None:
            if sha(original)!=f['before']:raise ValueError('backup checksum mismatch')
            atomic_copy(original,dest,f['before'])
        elif dest.exists():dest.unlink()  # Exact added payload only; no recursive deletion.
    return {'restored':True,'services_restarted':[],'diagnostics_deleted':False}

def install(manifest,package,root,*,owner_approved=False,fail_after=None,event=None):
    event=event or (lambda *a,**k:None)
    if not owner_approved:raise ValueError('explicit installation approval required')
    package=Path(package).resolve();root=Path(root).resolve()
    decision=check(manifest,package,root)
    if decision['status']=='already_installed':return decision
    backup=target(root,'data/backups/'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-stage20-'+uuid.uuid4().hex)
    event('backup_create',backup=str(backup),filesystem_write_attempted=True)
    backup.mkdir(parents=True,exist_ok=False)
    (backup/'transaction.json').write_text(json.dumps(manifest,indent=2))
    for f in manifest['files']:
        dest=target(root,f['path'])
        if dest.exists():
            out=target(backup/'originals',f['path']);out.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(dest,out)
    try:
        for i,f in enumerate(manifest['files'],1):
            event('payload_copy',path=f['path'],filesystem_write_attempted=True)
            dest=target(root,f['path']);dest.parent.mkdir(parents=True,exist_ok=True)
            atomic_copy(target(package,f['path']),dest,f['after'])
            if sha(dest)!=f['after']:raise ValueError('installed checksum mismatch')
            if fail_after==i:raise OSError('isolated failure injection')
    except Exception as original:
        # A failed evidence sink must never prevent restoring production targets.
        def report(*a,**k):
            try:event(*a,**k)
            except Exception:pass
        report('payload_rollback',rollback_attempted=True,original_error=str(original))
        try:
            rollback(backup,root)
        except Exception as exc:
            report('payload_rollback_failed',rollback_result='failed',error=str(exc));raise
        report('payload_rollback_complete',rollback_result='restored')
        raise
    return {'status':'files_installed_not_activated','backup':str(backup),
            'services_restarted':[],'services_enabled':[]}
