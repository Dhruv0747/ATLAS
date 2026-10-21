#!/usr/bin/env python3
"""Stage31b passive recorder: one JSON line per second to a file (flushed each line, survives disconnects).
Reads only /proc and the Vision Lab state file. No ROS, network, subprocess or writes elsewhere. Stops itself after DURATION s."""
import json, os, sys, time
OUT, DURATION = sys.argv[1], float(sys.argv[2])
HZ = os.sysconf('SC_CLK_TCK'); N = os.cpu_count(); ME = os.getpid()
STATE = '/run/user/%d/atlas-vision3d-viewer.json' % os.getuid()
def stat():
    return [int(x) for x in open('/proc/stat').readline().split()[1:9]]
def procs():
    o = {}
    for p in os.listdir('/proc'):
        if p.isdigit():
            try:
                s = open('/proc/%s/stat' % p).read(); r = s.rfind(')')
                f = s[r + 2:].split(); o[int(p)] = (s[s.find('(') + 1:r], int(f[11]) + int(f[12]))
            except Exception: pass
    return o
names = {}
def name(p, comm):
    if p not in names:
        try:
            c = [x.decode(errors='replace') for x in open('/proc/%d/cmdline' % p, 'rb').read().split(b'\0') if x]
            n = next((os.path.basename(x) for x in c if x.endswith('.py')), None) or (os.path.basename(c[0]) if c else '[' + comm + ']')
        except Exception: n = comm
        names[p] = n
    return names[p]
start = time.monotonic(); s0, p0, t0 = stat(), procs(), start
with open(OUT, 'a', buffering=1) as f:
    f.write(json.dumps({'start_wall': time.time(), 'ncpu': N, 'recorder_pid': ME}) + '\n')
    while time.monotonic() - start < DURATION:
        time.sleep(1.0)
        s1, p1, t1 = stat(), procs(), time.monotonic()
        d = [b - a for a, b in zip(s0, s1)]; tot = sum(d) or 1
        per = {}
        for p, (comm, v) in p1.items():
            dv = v - p0[p][1] if p in p0 else v
            pct = 100.0 * dv / HZ / (t1 - t0)
            if pct >= 1.5 or comm in ('astra_camera_no',): per[name(p, comm)[:40] + ':' + str(p)] = round(pct, 1)
        try: g = json.load(open(STATE)); guard = {'state': g.get('state'), 'elapsed': round(g.get('elapsed_s', 0), 2), 'cpu': (g.get('resources') or {}).get('cpu_percent'), 'failed': g.get('failed_resources'), 'astra': (g.get('astra_process') or {}).get('cpu_one_core_percent')}
        except Exception: guard = None
        f.write(json.dumps({'t': round(t1 - start, 2), 'wall': round(time.time(), 2), 'busy': round(100.0 * (tot - d[3] - d[4]) / tot, 2),
                            'user': round(100.0 * d[0] / tot, 2), 'nice': round(100.0 * d[1] / tot, 2), 'sys': round(100.0 * (d[2] + d[5] + d[6]) / tot, 2),
                            'guard': guard, 'per': per}) + '\n')
        s0, p0, t0 = s1, p1, t1
