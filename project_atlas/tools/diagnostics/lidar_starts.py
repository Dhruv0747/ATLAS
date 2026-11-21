#!/usr/bin/env python3
"""Read-only per-boot summary of RPLIDAR start attempts.

Input: journalctl --user -b <n> -u atlas-lidar -o short-monotonic > lidar_boot<n>.log
Codes in the sequence: T = no reply to the first query (SL_RESULT_OPERATION_TIMEOUT),
I = "Can not start scan: 80008000" (SL_RESULT_INVALID_DATA after health OK),
S = "Can not start scan: 80008002" (timeout at scan start), X = external stop, + = scanning.
"""
import re
import sys

for path in sys.argv[1:]:
    events = []
    for line in open(path, errors='replace'):
        m = re.match(r'\[\s*([0-9.]+)\]', line)
        if not m:
            continue
        t = float(m.group(1))
        if 'OPERATION_TIMEOUT' in line:
            events.append((t, 'T'))
        elif 'Can not start scan: 80008000' in line:
            events.append((t, 'I'))
        elif 'Can not start scan: 80008002' in line:
            events.append((t, 'S'))
        elif 'Can not start scan' in line:
            events.append((t, '?'))
        elif 'current scan mode' in line:
            events.append((t, '+'))
        elif 'Stopping Project ATLAS RPLIDAR' in line:
            events.append((t, 'X'))
    kinds = [k for _, k in events]
    first = next((t for t, k in events if k == '+'), None)
    print(f'{path}: first scan at {first} s after boot; failures T={kinds.count("T")} I={kinds.count("I")} '
          f'S={kinds.count("S")} other={kinds.count("?")}; stops={kinds.count("X")}; sequence={"".join(kinds)}')
