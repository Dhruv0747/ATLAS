"""One-shot boot-time evidence for the planned Recovery update (stdlib only, no ROS).

Runs once per boot, only when the ARMED marker exists (consumed at start). Every 1 s it records
whole-Jetson CPU (/proc/stat), RAM (MemAvailable), hottest thermal zone, and Recovery's cgroup
CPU, PIDs and NRestarts. It never starts, stops, restarts or reloads anything.

The 75 % CPU / 80 % RAM / 70 C limits are applied unchanged. Boot is not an exemption: any limit
breach from Recovery's first appearance to +EVAL_S fails the evaluation.

The only automatic action is in CANDIDATE mode: if Recovery is failed or has restarted, or the
evaluation fails for any reason (including a limit breach), the exact original script bytes are restored (atomic same-directory replace). systemd's existing restart
policy then runs the known-good script. The monitor issues no systemctl start/stop/restart.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(os.environ.get('ATLAS_BOOT_ROOT', '/'))
HOME = Path(os.environ.get('HOME', '/home/jetson'))
PKG = Path(__file__).resolve().parent
UNIT = 'atlas-sensor-recovery.service'
CGROUP = 'sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice/' + UNIT
TARGET = HOME / 'project_atlas/scripts/atlas_sensor_recovery.py'
LIVE = '5f44cc1fbd7cdc65b8af17abeb9ecd41cec0a8c8f3ee8274fa9b34362633193a'
CAND = '4af4ddade5bf998d3fbb9012a0ebe50902c83d922a55a3a8e97ebb8f01e19e4d'
MTIME_NS = 1793532594436767674          # 2026-11-02 15:29:54.436767674 +0530 (original mtime)
CPU_MAX, RAM_MAX, TEMP_MAX = 75.0, 80.0, 70.0
DURATION_S, EVAL_S = 300.0, 120.0
EARLY_USAGE_USEC = 50000   # Recovery CPU already used when sampling begins; its startup is ~1.7 CPU-s


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cpu_ticks():
    f = (ROOT / 'proc/stat').read_text().split('\n', 1)[0].split()[1:]
    t = [int(x) for x in f]
    return sum(t[:8]), t[3] + t[4]                # total, idle+iowait


def ram_pct():
    m = dict(line.split(':', 1) for line in (ROOT / 'proc/meminfo').read_text().splitlines() if ':' in line)
    total, avail = int(m['MemTotal'].split()[0]), int(m['MemAvailable'].split()[0])
    return 100.0 * (total - avail) / total


def temp_c():
    temps = []
    for z in sorted((ROOT / 'sys/class/thermal').glob('thermal_zone*/temp')):
        try:
            temps.append(int(z.read_text()) / 1000.0)
        except (OSError, ValueError):
            pass
    return max(temps) if temps else None


def recovery_cgroup():
    base = ROOT / CGROUP
    try:
        usage = int(dict(l.split() for l in (base / 'cpu.stat').read_text().splitlines())['usage_usec'])
        pids = (base / 'cgroup.procs').read_text().split()
        return usage, pids
    except (OSError, KeyError, ValueError):
        return None, []


def default_show():
    out = subprocess.run(['/usr/bin/systemctl', '--user', 'show', UNIT, '-p', 'ActiveState',
                          '-p', 'NRestarts', '-p', 'MainPID'], capture_output=True, text=True, timeout=2).stdout
    return dict(l.split('=', 1) for l in out.splitlines() if '=' in l)


def restore_original(rollback):
    """Atomic exact-byte restore; refuses unknown bytes. Returns a short result string."""
    cur = sha(TARGET)
    if cur == LIVE:
        return 'already-original'
    if cur != CAND:
        return 'refused-unknown-bytes'
    data = Path(rollback).read_bytes()
    if hashlib.sha256(data).hexdigest() != LIVE:
        return 'refused-bad-rollback-bytes'
    tmp = TARGET.with_name(TARGET.name + '.restore')
    tmp.write_bytes(data)
    os.chmod(tmp, 0o644)
    os.utime(tmp, ns=(MTIME_NS, MTIME_NS))
    os.replace(tmp, TARGET)
    return 'restored' if sha(TARGET) == LIVE else 'restore-verify-failed'


def evaluate(rows, mode, recovery_seen, initial=(None, None)):
    breaches, start = [], recovery_seen
    for r in rows:
        if start is not None and start <= r['uptime'] <= start + EVAL_S:
            for key, lim in (('cpu', CPU_MAX), ('ram', RAM_MAX), ('temp', TEMP_MAX)):
                if r[key] is not None and r[key] >= lim:
                    breaches.append({'uptime': r['uptime'], key: r[key]})
    pre = [r for r in rows if start is None or r['uptime'] < start]
    last = rows[-1] if rows else {}
    healthy = last.get('active') == 'active' and last.get('nrestarts') == '0'
    # Start window observed: Recovery appeared after sampling began, or had used <= 50 ms CPU when it began
    # (it is forked milliseconds after this monitor; its ~1.7 CPU-s startup then lies inside measured windows).
    present0, usage0 = initial
    covered = bool(rows) and start is not None and (
        not present0 or (usage0 is not None and usage0 <= EARLY_USAGE_USEC))
    long_enough = bool(rows) and start is not None and rows[-1]['uptime'] >= start + EVAL_S
    verdict = 'PASS' if covered and long_enough and not breaches and healthy and not any(r.get('action') for r in rows) else 'FAIL'
    return {
        'mode': mode, 'verdict': verdict, 'recovery_first_seen_uptime': start,
        'breaches_in_eval_window': breaches,
        'pre_recovery_peak_cpu': max((r['cpu'] for r in pre), default=None),
        'peak_cpu': max((r['cpu'] for r in rows), default=None),
        'peak_ram': max((r['ram'] for r in rows), default=None),
        'peak_temp': max((r['temp'] for r in rows if r['temp'] is not None), default=None),
        'start_window_observed': covered, 'recovery_at_monitor_start': {'present': present0, 'usage_usec': usage0}, 'eval_window_complete': long_enough,
        'recovery_final_state': last.get('active'), 'nrestarts_final': last.get('nrestarts'),
        'actions': [r['action'] for r in rows if r.get('action')],
        'limits': {'cpu_pct': CPU_MAX, 'ram_pct': RAM_MAX, 'temp_c': TEMP_MAX, 'eval_s': EVAL_S},
    }


def run(show=default_show, sleep=time.sleep, duration=DURATION_S):
    armed = PKG / 'ARMED'
    if not armed.exists():
        return None                                   # one-shot: nothing to do on later boots
    mode = armed.read_text().strip()
    armed.rename(PKG / 'ARMED.consumed')
    boot = (ROOT / 'proc/sys/kernel/random/boot_id').read_text().strip()
    out = HOME / 'project-atlas-migration' / ('boot-evidence-' + boot[:8])
    out.mkdir(parents=True, exist_ok=True)
    rows, seen, prev = [], None, cpu_ticks()
    usage0, pids0 = recovery_cgroup()
    up0 = float((ROOT / 'proc/uptime').read_text().split()[0])
    if pids0:
        seen = up0                                   # already forked when sampling began
    t_end = time.monotonic() + duration
    with open(out / 'samples.jsonl', 'a') as log:
        while time.monotonic() < t_end:
            sleep(1.0)
            cur = cpu_ticks()
            dt, didle = cur[0] - prev[0], cur[1] - prev[1]
            prev = cur
            usage, pids = recovery_cgroup()
            try:
                st = show()
            except (OSError, subprocess.SubprocessError, ValueError) as exc:   # e.g. timeout under boot load
                st = {'error': type(exc).__name__}
            row = {'uptime': float((ROOT / 'proc/uptime').read_text().split()[0]),
                   'cpu': 100.0 * (dt - didle) / dt if dt > 0 else None, 'ram': ram_pct(), 'temp': temp_c(),
                   'recovery_usage_usec': usage, 'recovery_pids': pids,
                   'show_error': st.get('error'), 'active': st.get('ActiveState'), 'nrestarts': st.get('NRestarts'), 'main_pid': st.get('MainPID')}
            if seen is None and pids:
                seen = row['uptime']
            # A fresh user manager starts NRestarts at 0; any restart or failed state is unhealthy.
            unhealthy = row['active'] == 'failed' or (row['nrestarts'] not in (None, '0'))
            if mode == 'candidate' and unhealthy and not any(r.get('action') for r in rows):
                row['action'] = 'fail-closed:' + restore_original(PKG / 'atlas_sensor_recovery.rollback.py')
            rows.append(row)
            log.write(json.dumps(row) + '\n'); log.flush(); os.fsync(log.fileno())
    summary = evaluate(rows, mode, seen, (bool(pids0), usage0))
    if mode == 'candidate' and summary['verdict'] == 'FAIL' and not summary['actions']:
        # Any failed evaluation (including a limit breach) rejects the candidate: restore the original
        # bytes for the next start. The running process is not stopped; a spike already measured cannot be
        # undone by stopping it, and stopping would remove background sensor recovery.
        summary['actions'].append('fail-closed:' + restore_original(PKG / 'atlas_sensor_recovery.rollback.py'))
    summary['boot_id'] = boot
    summary['script_sha256_at_end'] = sha(TARGET)
    (out / 'summary.json').write_text(json.dumps(summary, indent=1) + '\n')
    return summary


if __name__ == '__main__':
    run()
