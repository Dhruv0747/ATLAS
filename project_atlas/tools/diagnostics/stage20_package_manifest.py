"""Prepare a read-only diagnostic package manifest; never install or enable it.

Hash actual built files, not expected imaginary artifacts. Readiness defaults
false and cannot be asserted by this generator. Existing stage installer remains
the future installation mechanism, subject to Stage 20's strict identity guard.
"""
import argparse
import hashlib
import json
from pathlib import Path

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def prepare(files, baseline, source_commit):
    return {'schema':1,'source_commit':source_commit,'deployment_ready':False,
        'default':'OFF','stage17b':'HOLD','installed':False,
        'binary_files':{str(p):sha(p) for p in files},'approved_live_baseline':baseline,
        'pending':['complete failure injection','startup ordering qualification',
                   'production opt-in adapter','existing-installer rollback rehearsal',
                   'full fidelity comparisons'],
        'affected_services_if_later_approved':['atlas-ekf.service','atlas-localization.service',
            'atlas-mission-control.service','atlas-checkpoint-capture.service'],
        'restart_now':False,'accepted_map_modified':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path)
    p.add_argument('--source-commit',required=True);p.add_argument('files',nargs='+',type=Path)
    a=p.parse_args()
    if a.output.exists():p.error('preserve existing package evidence; new output required')
    result=prepare(a.files,{},a.source_commit)
    with a.output.open('x') as f:json.dump(result,f,indent=2)
