#!/usr/bin/env python3
"""Render a review package only. Never installs, activates, or changes firewall."""
import argparse
import hashlib
from pathlib import Path
import shutil

SHA='caa6ebe571e4ae57aa2be5be9bc80bea00252c6fb9c2897387edc762caf8b0f9'

def trial_bytes(data):
    # Trial artifact used CRLF; Git's canonical source uses LF. Reconstruct only
    # those exact bytes and require the trial SHA, independent of checkout OS.
    if hashlib.sha256(data).hexdigest()!=SHA:
        data=data.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
    if hashlib.sha256(data).hexdigest()!=SHA: raise ValueError('trial exporter hash mismatch')
    return data

def prepare(output, uid):
    if not 1 <= uid <= 2147483647: raise ValueError('invalid target service UID')
    here=Path(__file__).resolve().parent
    exporter=here.parents[2]/'project_atlas/scripts/atlas_health_exporter.py'
    data=trial_bytes(exporter.read_bytes())
    output.mkdir(parents=True,exist_ok=False)
    (output/'atlas_health_exporter.py').write_bytes(data)
    for name in ('guard.py','atlas-monitor.nft','atlas-monitoring-firewall.service','atlas-monitoring-watchdog.service'):
        shutil.copyfile(here/name,output/name)
    text=(here/'atlas-monitoring-exporter.service.in').read_text().replace('@JETSON_UID@',str(uid))
    (output/'atlas-monitoring-exporter.service').write_text(text)
    (output/'TARGET_UID').write_text(str(uid)+'\n')
    manifest=''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in sorted(output.iterdir()))
    (output/'SHA256SUMS').write_text(manifest)
    print(hashlib.sha256(manifest.encode()).hexdigest()+'  SHA256SUMS')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--uid',type=int,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();prepare(args.output,args.uid)
