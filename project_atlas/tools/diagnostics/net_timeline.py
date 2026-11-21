#!/usr/bin/env python3
"""Read-only Wi-Fi / route / Tailscale timeline from saved journal extracts.

Input: files written on the Jetson with
    journalctl -b <n> -o short-iso -u NetworkManager -u wpa_supplicant -u tailscaled -u ModemManager > net_boot<n>.log
Usage: net_timeline.py net_boot*.log            # event timeline
       net_timeline.py --summary net_boot*.log  # per-AP DHCP outcome and cellular default-route periods
BSSIDs are replaced by short AP labels; SSIDs are never printed.
"""
import collections
import datetime as dt
import re
import sys

AP = {'b4:a7:c6:41:fc:99': 'A2.4', 'b4:a7:c6:41:fc:9a': 'A5', 'f0:ed:b8:33:16:49': 'B2.4',
      'f0:ed:b8:33:16:4a': 'B5', '8c:a3:99:e7:a3:c1': 'X2.4', '8c:a3:99:e7:a3:c2': 'X5'}
PATTERNS = [
    ('ASSOC', re.compile(r'Associated with ([0-9a-f:]{17})')),
    ('DHCP_RESTART', re.compile(r'ip:dhcp4: restarting')),
    ('LEASE', re.compile(r'dhcp4 \(wlP1p1s0\): state changed new lease')),
    ('IPCFG_UNAVAIL', re.compile(r'ip-config-unavailable')),
    ('ROUTE_CELL', re.compile(r'\(usb0\) as default for IPv4')),
    ('ROUTE_WIFI', re.compile(r'\(wlP1p1s0\) as default for IPv4')),
    ('WIFI_DISC', re.compile(r'CTRL-EVENT-DISCONNECTED.*reason=(\d+)')),
    ('TS_HOME', re.compile(r'home is now derp-\d+ \((\w+)\)')),
    ('TS_MAJOR', re.compile(r'LinkChange: major')),
]


def boot_key(path):
    m = re.search(r'boot(-?\d+)', path)
    return int(m.group(1)) if m else 0


def timeline(paths):
    for f in sorted(paths, key=boot_key):
        print('=====', f)
        for line in open(f, errors='replace'):
            for kind, pat in PATTERNS:
                m = pat.search(line)
                if m:
                    print(line[5:19], kind, *[AP.get(g, g) for g in m.groups()])


def summary(paths):
    leases = collections.defaultdict(list)
    assoc = collections.Counter()
    no_lease = collections.Counter()
    cell = []
    for f in paths:
        cur = t0 = cell_start = None
        for line in open(f, errors='replace'):
            t = dt.datetime.strptime(line[:19], '%Y-%m-%dT%H:%M:%S')
            m = re.search(r'Associated with ([0-9a-f:]{17})', line)
            if m:
                if cur and t0:
                    no_lease[cur] += 1      # roamed again before any lease
                cur, t0 = AP.get(m.group(1), m.group(1)), t
                assoc[cur] += 1
            if 'dhcp4 (wlP1p1s0): state changed new lease' in line and cur and t0:
                leases[cur].append((t - t0).total_seconds())
                t0 = None
            if 'ip-config-unavailable' in line and cur and t0:
                no_lease[cur] += 1
                t0 = None
            if '(usb0) as default for IPv4' in line:
                cell_start = t
            if '(wlP1p1s0) as default for IPv4' in line and cell_start:
                cell.append((cell_start.isoformat(), (t - cell_start).total_seconds()))
                cell_start = None
        if cell_start:
            cell.append((cell_start.isoformat(), 'open at end of journal'))
    for k in sorted(assoc):
        ok = sorted(leases[k])
        print(f'{k:5} associations={assoc[k]:3} lease={len(ok):3} no_lease={no_lease[k]:2} '
              f'lease_s median={ok[len(ok) // 2] if ok else "-"} max={max(ok) if ok else "-"}')
    print('cellular default-route periods (start, seconds):')
    for row in sorted(cell):
        print('  ', *row)


if __name__ == '__main__':
    args = sys.argv[1:]
    if args and args[0] == '--summary':
        summary(args[1:])
    else:
        timeline(args)
