"""One owner-run ranked native capture. No install, control or ROS participant."""
import hashlib
import os
from pathlib import Path
import sys
import time
import types

HELPER_SHA = '2b0cd1ee5872070ee21c93780445e8296b9f1a2574b84ad3e7375e98bc959e18'
STAGE = Path('/home/jetson/project-atlas-migration/ranked-cpu-20261024')
UNITS = ('atlas-camera.service', 'rover-base-telemetry.service',
         'atlas-cmd-vel-mux.service', 'atlas-ekf.service', 'atlas-localization.service',
         'atlas-lidar.service', 'atlas-voice-companion.service',
         'atlas-safety-status.service', 'atlas-localization-monitor.service',
         'atlas-mission-control.service', 'rover-status-web.service')
GROUPS = {'/user.slice/user-1000.slice/user@1000.service/app.slice/' + u for u in UNITS}


def stat_fields(text):
    fields = text.rsplit(')', 1)[1].split()
    return int(fields[11]) + int(fields[12]), int(fields[19])


def allowed(executable, cgroup, uid, owner):
    return uid == owner and cgroup in GROUPS and (
        executable in ('/usr/bin/python3.10', '/usr/bin/python3', '/usr/bin/bash') or
        executable.startswith('/opt/ros/humble/lib/'))


def snapshot(original, proc=Path('/proc')):
    """PID rows are totals; TID rows are subsets. NEVER sum both together."""
    rows = {}
    for root in proc.iterdir():
        if not root.name.isdigit():
            continue
        try:
            ticks, birth = stat_fields((root/'stat').read_text())
            cgroup = (root/'cgroup').read_text().strip()
            if not cgroup.startswith('0::') or '\n' in cgroup:
                continue
            cgroup = cgroup[3:]
            row = dict(ticks=ticks, birth=birth, tgid=int(root.name),
                       name=(root/'comm').read_text().strip(), cgroup=cgroup,
                       kind='process_total', profile_eligible=False)
            rows['process:'+root.name] = row
            executable = str((root/'exe').resolve(strict=True))
            if not allowed(executable, cgroup, root.stat().st_uid, os.getuid()):
                continue
            for tid, data in original(int(root.name)).items():
                rows[tid] = dict(data, tgid=int(root.name), cgroup=cgroup,
                                 executable=executable, kind='thread',
                                 process_birth=birth, profile_eligible=True)
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
    return rows


def choose(before, after, count=6):
    ranked = []
    for tid, row in after.items():
        old = before.get(tid)
        if not row.get('profile_eligible') or old is None:
            continue
        identity = ('birth', 'process_birth', 'tgid', 'cgroup', 'executable')
        if any(row.get(k) != old.get(k) for k in identity):
            continue
        delta = row['ticks'] - old['ticks']
        if delta > 0:
            ranked.append((delta, int(tid), row['birth']))
    ranked.sort(reverse=True)
    if not ranked:
        raise RuntimeError('No stable CPU-active eligible ATLAS threads')
    return {str(tid): birth for _, tid, birth in ranked[:count]}


def command(perf, pid, output, tids):
    if pid <= 1 or not 1 <= len(tids) <= 6 or len(set(tids)) != len(tids) or any(t <= 1 for t in tids):
        raise ValueError('Invalid bounded target set')
    return ['/usr/bin/timeout', '--signal=INT', '--kill-after=2s', '23s', str(perf),
            'record', '-t', ','.join(map(str, tids)), '--no-inherit', '--per-thread',
            '--no-bpf-event', '--num-thread-synthesize', '1', '-e', 'cpu-clock:u',
            '-F', '49', '--strict-freq', '--call-graph', 'dwarf,4096',
            '-m', '64', '--no-buildid', '--no-buildid-cache', '-k', 'CLOCK_MONOTONIC',
            '-o', str(output), '--', '/usr/bin/sleep', '20']


def load_helper(path):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != HELPER_SHA:
        raise RuntimeError('Unreviewed helper hash')
    source = raw.decode()
    replacements = {
        '        import stationary_gate as G': "        import stationary_gate as G\n        G.UNITS = tuple(dict.fromkeys(G.UNITS + EXTRA_UNITS))",
        'deadline = time.monotonic()+12': 'deadline = time.monotonic()+22',
    }
    for old, new in replacements.items():
        if source.count(old) != 1:
            raise RuntimeError('Unexpected helper structure: '+old)
        source = source.replace(old, new)
    module = types.ModuleType('ranked_profile_helper')
    exec(compile(source, str(path), 'exec'), module.__dict__)
    module.EXTRA_UNITS = tuple(u for u in UNITS if u != 'rover-status-web.service')
    module.STAGE = STAGE
    module.HASHES.update({
        'scripts/atlas_status_web.py': 'acb9fe18d384a7e2c06c24e1ab3abd5c3ebc1b46b5d26902ec39e1a3155d7439',
        'scripts/atlas_voice_companion.py': 'a88ff78df1ae2dded4f9984cdcf5e94d5335d1d12c77fd9c9131219725298870',
        'scripts/atlas_safety_status.py': '94f52bcc1d535378adf6d4f54f6d29fc52f0cd7b12b11a8da0df39117f510bd4',
    })
    original = module.thread_snapshot
    cache = [0.0, {}]
    def current(_):
        now = time.monotonic()
        if now-cache[0] > .3:
            cache[:] = [now, snapshot(original)]
        return cache[1]
    module.thread_snapshot = current
    selected_identities = {}
    def select(a, b, count=2):
        selected = choose(a, b, 6)
        for tid in selected:
            selected_identities[tid] = {k:b[tid][k] for k in
                ('birth', 'process_birth', 'tgid', 'cgroup', 'executable')}
        return selected
    module.select_hot_threads = select
    original_require = module.require_target_threads
    def require(rows, selected):
        original_require(rows, selected)
        for tid, expected in selected_identities.items():
            if any(rows.get(tid, {}).get(k) != v for k,v in expected.items()):
                raise RuntimeError('Selected process identity or service membership changed')
    module.require_target_threads = require
    module.command = lambda pid, output, tids: command(module.PERF, pid, output, tids)
    return module


def main():
    if sys.argv[1:] != ['--diagnostic-cpu-report-only']:
        raise SystemExit('Requires the explicitly approved diagnostic-only CPU reporting flag')
    return load_helper(Path(__file__).with_name('native_dashboard_cpu_once.py')).main()


if __name__ == '__main__':
    sys.exit(main())
