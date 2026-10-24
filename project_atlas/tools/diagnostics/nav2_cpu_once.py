"""Owner-run native Nav2 profile; no production mutation or CPU exception."""
import hashlib
import os
from pathlib import Path
import sys
import types

HELPER_SHA = '2b0cd1ee5872070ee21c93780445e8296b9f1a2574b84ad3e7375e98bc959e18'
STAGE = Path('/home/jetson/project-atlas-migration/nav2-cpu-20261024')
CGROUP = '/user.slice/user-1000.slice/user@1000.service/app.slice/atlas-localization.service'
BINARIES = {
    '/opt/ros/humble/lib/' + package + '/' + binary
    for package, binary in (
        ('nav2_map_server', 'map_server'), ('nav2_amcl', 'amcl'),
        ('nav2_lifecycle_manager', 'lifecycle_manager'),
        ('nav2_controller', 'controller_server'), ('nav2_planner', 'planner_server'),
        ('nav2_behaviors', 'behavior_server'), ('nav2_bt_navigator', 'bt_navigator'),
        ('nav2_waypoint_follower', 'waypoint_follower'))}
LAUNCH = [b'/usr/bin/python3', b'/opt/ros/humble/bin/ros2', b'launch',
          b'tortoisebot_bringup', b'atlas_localization.launch.py',
          b'map:=/home/jetson/project_atlas/maps/atlas_latest.yaml']


def verify_launch(pid):
    if Path('/proc', str(pid), 'cmdline').read_bytes().rstrip(b'\0').split(b'\0') != LAUNCH:
        raise RuntimeError('Not the reviewed Nav2 launch command')


def group_snapshot(main_pid, snapshot, proc=Path('/proc'),
                   cgroups=Path('/sys/fs/cgroup')):
    ids = [int(p) for p in (cgroups / CGROUP.lstrip('/') / 'cgroup.procs').read_text().split()]
    if main_pid not in ids or not 2 <= len(ids) <= 20 or len(set(ids)) != len(ids):
        raise RuntimeError('Invalid Nav2 process group')
    result = {}
    for pid in ids:
        root = proc / str(pid)
        if root.stat().st_uid != os.getuid():
            raise RuntimeError('Nav2 process owner changed')
        if root.joinpath('cgroup').read_text().strip() != '0::' + CGROUP:
            raise RuntimeError('Nav2 process group changed')
        executable = str(root.joinpath('exe').resolve(strict=True))
        if pid != main_pid and executable not in BINARIES:
            raise RuntimeError('Unexpected Nav2 executable: ' + executable)
        for tid, row in snapshot(pid).items():
            result[tid] = dict(row, tgid=pid, executable=executable,
                               cgroup=CGROUP, profile_eligible=pid != main_pid)
    return result


def load_helper(path):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != HELPER_SHA:
        raise RuntimeError('Profiling helper hash mismatch')
    source = raw.decode()
    old = "        if str(LIVE/TARGET_SCRIPT).encode() not in Path('/proc', str(pid), 'cmdline').read_bytes().split(b'\\0'):\n            raise RuntimeError('Not the reviewed target command')"
    if source.count(old) != 1:
        raise RuntimeError('Unexpected target validation structure')
    source = source.replace(old, '        verify_launch(pid)')
    old = '        import stationary_gate as G'
    if source.count(old) != 1:
        raise RuntimeError('Unexpected safety helper structure')
    source = source.replace(old, old + "\n        G.UNITS = G.UNITS + ('atlas-voice-companion.service', 'atlas-safety-status.service', 'atlas-localization-monitor.service', 'atlas-mission-control.service')")
    module = types.ModuleType('atlas_nav2_profile_helper')
    exec(compile(source, str(path), 'exec'), module.__dict__)
    module.verify_launch = verify_launch
    module.STAGE = STAGE
    module.TARGET_UNIT = 'atlas-localization.service'
    module.HASHES = dict(module.HASHES, **{
        'scripts/atlas_status_web.py': 'acb9fe18d384a7e2c06c24e1ab3abd5c3ebc1b46b5d26902ec39e1a3155d7439',
        'scripts/atlas_voice_companion.py': 'a88ff78df1ae2dded4f9984cdcf5e94d5335d1d12c77fd9c9131219725298870',
        'scripts/atlas_safety_status.py': '94f52bcc1d535378adf6d4f54f6d29fc52f0cd7b12b11a8da0df39117f510bd4',
    })
    original_snapshot = module.thread_snapshot
    identities = None
    def stable_snapshot(pid):
        nonlocal identities
        rows = group_snapshot(pid, original_snapshot)
        current = {r['tgid']: (r['birth'], r['executable']) for t,r in rows.items()
                   if int(t) == r['tgid']}
        if identities is not None and current != identities:
            raise RuntimeError('Nav2 child process identity changed')
        identities = current
        return rows
    module.thread_snapshot = stable_snapshot
    original_select = module.select_hot_threads
    module.select_hot_threads = lambda a, b, count=2: original_select(
        {k:v for k,v in a.items() if v['profile_eligible']},
        {k:v for k,v in b.items() if v['profile_eligible']}, count)
    # The inherited bounded perf command remains user-space only, 19 Hz,
    # 4096-byte DWARF stacks, two native TIDs, no inheritance, ten seconds.
    return module


def main():
    if sys.argv[1:]:
        raise SystemExit('No options accepted; CPU/RAM/temperature limits remain strict')
    module = load_helper(Path(__file__).with_name('native_dashboard_cpu_once.py'))
    return module.main()


if __name__ == '__main__':
    sys.exit(main())
