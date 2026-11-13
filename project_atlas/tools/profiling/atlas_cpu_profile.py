#!/usr/bin/env python3
"""Read-only CPU/RAM profile of the ATLAS stack, grouped by systemd unit and process.

Samples /proc/<pid>/stat twice (default 30 s apart), attributes each process to its systemd unit via
/proc/<pid>/cgroup, and names ROS nodes from their command line (__node:= or the script name).
Usage: python3 atlas_cpu_profile.py [--seconds 30] [--json out.json] [--label NAME]
CPU % is per core (600 % = all six Orin Nano cores busy).
"""
import argparse, json, os, re, time

HZ = os.sysconf('SC_CLK_TCK')


def procs():
    out = {}
    for d in os.listdir('/proc'):
        if not d.isdigit():
            continue
        try:
            with open(f'/proc/{d}/stat') as f:
                s = f.read()
            rest = s[s.rfind(')') + 2:].split()
            ticks = int(rest[11]) + int(rest[12])            # utime + stime
            rss_kb = int(rest[21]) * os.sysconf('SC_PAGE_SIZE') // 1024
            with open(f'/proc/{d}/cgroup') as f:
                cg = f.read()
            m = re.search(r'/([^/]+\.(?:service|scope))\s*$', cg, re.M)
            unit = m.group(1) if m else 'kernel/other'
            with open(f'/proc/{d}/cmdline', 'rb') as f:
                cmd = f.read().replace(b'\0', b' ').decode(errors='replace').strip()
            out[int(d)] = (ticks, rss_kb, unit, cmd)
        except (FileNotFoundError, ProcessLookupError, PermissionError, IndexError, ValueError):
            pass
    return out


def node_name(cmd):
    m = re.search(r'__node:=(\S+)', cmd)
    if m:
        return m.group(1)
    for tok in cmd.split():
        b = os.path.basename(tok)
        if b.endswith('.py') or (b and not b.startswith('-') and b not in ('python3', 'bash', 'sh', '/usr/bin/python3')):
            if b not in ('python3', 'python3.10', 'bash', 'sh', 'ros2'):
                return b[:48]
    return (cmd.split() or ['?'])[0][:48]


def stat_cpu():
    with open('/proc/stat') as f:
        v = list(map(int, f.readline().split()[1:]))
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seconds', type=float, default=30.0)
    ap.add_argument('--json')
    ap.add_argument('--label', default='')
    ap.add_argument('--top', type=int, default=40)
    a = ap.parse_args()
    c0, p0, t0 = stat_cpu(), procs(), time.time()
    time.sleep(a.seconds)
    c1, p1, t1 = stat_cpu(), procs(), time.time()
    dt = t1 - t0
    d = [y - x for x, y in zip(c0, c1)]
    tot = sum(d) or 1
    sysw = {'user': d[0] / tot, 'nice': d[1] / tot, 'system': d[2] / tot, 'idle': d[3] / tot,
            'iowait': d[4] / tot, 'irq': (d[5] + d[6]) / tot}
    rows = []
    for pid, (tk, rss, unit, cmd) in p1.items():
        if pid in p0 and p0[pid][3] == cmd:
            cpu = 100.0 * (tk - p0[pid][0]) / HZ / dt
            rows.append({'pid': pid, 'unit': unit, 'node': node_name(cmd), 'cpu_pct': round(cpu, 1), 'rss_mb': round(rss / 1024, 1)})
    units = {}
    for r in rows:
        u = units.setdefault(r['unit'], {'unit': r['unit'], 'cpu_pct': 0.0, 'rss_mb': 0.0, 'procs': 0})
        u['cpu_pct'] += r['cpu_pct']; u['rss_mb'] += r['rss_mb']; u['procs'] += 1
    ulist = sorted(units.values(), key=lambda u: -u['cpu_pct'])
    for u in ulist:
        u['cpu_pct'] = round(u['cpu_pct'], 1); u['rss_mb'] = round(u['rss_mb'], 1)
    rows.sort(key=lambda r: -r['cpu_pct'])
    with open('/proc/loadavg') as f:
        load = f.read().split()[:3]
    total = round(sum(u['cpu_pct'] for u in ulist), 1)
    print(f'ATLAS CPU profile {a.label} {time.strftime("%Y-%m-%d %H:%M:%S")}  window {dt:.0f} s  load {" ".join(load)}')
    print('system: ' + '  '.join(f'{k} {v*100:.1f}%' for k, v in sysw.items()) + f'   process total {total}% of 600%')
    print(f'\n{"unit":46s} {"CPU%":>6s} {"RSS MB":>7s} procs')
    for u in ulist[:a.top]:
        if u['cpu_pct'] >= 0.5:
            print(f'{u["unit"][:46]:46s} {u["cpu_pct"]:6.1f} {u["rss_mb"]:7.0f} {u["procs"]:5d}')
    print(f'\n{"process / node":40s} {"unit":36s} {"CPU%":>6s} {"RSS":>6s}')
    for r in rows[:a.top]:
        print(f'{r["node"][:40]:40s} {r["unit"][:36]:36s} {r["cpu_pct"]:6.1f} {r["rss_mb"]:6.0f}')
    if a.json:
        with open(a.json, 'w') as f:
            json.dump({'label': a.label, 'time': t1, 'window_s': dt, 'load': load, 'system': sysw,
                       'process_total_pct': total, 'units': ulist, 'processes': rows}, f, indent=1)


if __name__ == '__main__':
    main()
