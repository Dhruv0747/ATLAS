#!/usr/bin/env python3
"""Read-only non-secret network configuration snapshot; does not apply settings."""
import argparse
import json
import os
from pathlib import Path
import subprocess


def run(*args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=15)
    return dict(code=result.returncode, out=result.stdout.strip(), error=result.stderr.strip())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('new file required')
    uuid = run('nmcli','-g','GENERAL.CON-UUID','device','show','wlP1p1s0')['out']
    fields = 'connection.uuid,connection.autoconnect,connection.autoconnect-priority,802-11-wireless.bssid,802-11-wireless.powersave,ipv4.method,ipv4.route-metric'
    data = dict(profile=run('nmcli','-f',fields,'connection','show',uuid),
                power_save=run('iw','dev','wlP1p1s0','get','power_save'),
                regdomain=run('iw','reg','get'), routes=run('ip','-j','route','show'),
                rules=run('ip','-j','rule','show'))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(args.out, os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as handle:
        json.dump(data,handle,indent=2)
    print('Saved non-secret configuration; no network changes:', args.out)


if __name__ == '__main__':
    main()
