#!/usr/bin/env python3
"""Passive per-second CPU time series (reads /proc only) while an optional command runs after a delay.
Usage: joinprof.py <total_s> <delay_s> [command...]   The command is whatever the operator passes (e.g. a ros2 CLI query)."""
import os, sys, time, json, subprocess
T, D = float(sys.argv[1]), float(sys.argv[2]); CMD = sys.argv[3:]
HZ = os.sysconf('SC_CLK_TCK'); N = os.cpu_count()
def st():
    f = [int(x) for x in open('/proc/stat').readline().split()[1:9]]
    return f
def procs():
    o = {}
    for p in os.listdir('/proc'):
        if p.isdigit():
            try:
                s = open('/proc/%s/stat' % p).read(); r = s.rfind(')'); f = s[r+2:].split()
                o[int(p)] = int(f[11]) + int(f[12])
            except Exception: pass
    return o
def name(p):
    try:
        c = open('/proc/%d/cmdline' % p, 'rb').read().split(b'\0')
        c = [x.decode(errors='replace') for x in c if x]
        for x in c:
            if x.endswith('.py') or '/lib/' in x: return os.path.basename(x)
        return os.path.basename(c[0]) if c else open('/proc/%d/comm' % p).read().strip()
    except Exception: return '?'
series = []; started = None; child = None
s0, p0, t0 = st(), procs(), time.monotonic(); start = t0
names = {}
while time.monotonic() - start < T:
    time.sleep(1.0)
    if CMD and child is None and time.monotonic() - start >= D:
        started = round(time.monotonic() - start, 2)
        child = subprocess.Popen(CMD, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    s1, p1, t1 = st(), procs(), time.monotonic()
    d = [b - a for a, b in zip(s0, s1)]; tot = sum(d)
    busy = 100.0 * (tot - d[3] - d[4]) / tot; nice = 100.0 * d[1] / tot; sysc = 100.0 * (d[2] + d[5] + d[6]) / tot
    per = {}
    for p, v in p1.items():
        dv = v - p0.get(p, v if p in p0 else 0)
        if p not in p0: dv = v
        if dv > 0: per[p] = 100.0 * dv / HZ / (t1 - t0)
    for p in per:
        if p not in names: names[p] = name(p)
    series.append({'t': round(t1 - start, 2), 'busy': round(busy, 2), 'nice': round(nice, 2), 'sys_irq': round(sysc, 2),
                   'per': {str(p): round(v, 1) for p, v in per.items() if v >= 1.0}})
    s0, p0, t0 = s1, p1, t1
rc = child.wait(timeout=60) if child else None
print(json.dumps({'cmd': CMD, 'cmd_started_s': started, 'rc': rc, 'names': {str(k): v for k, v in names.items()}, 'series': series}))
