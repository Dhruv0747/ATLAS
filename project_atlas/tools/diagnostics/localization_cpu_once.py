"""One owner-run, strict-guard localization Python-thread profile.

Private adaptation of a hash-pinned diagnostic helper, never production code.
No GIL filter: NumPy can release the GIL. Native thread ticks accompany stacks.
"""
import hashlib
from pathlib import Path
import sys
import types

HELPER_SHA = '2b0cd1ee5872070ee21c93780445e8296b9f1a2574b84ad3e7375e98bc959e18'
STAGE = Path('/home/jetson/project-atlas-migration/localization-cpu-20261024')
MONITOR_SHA = 'cddbbc8d44a07b57c62a6ec4160cbbe9c0b02e4fe82d91ab126bafd66f68839b'
CORE_SHA = 'd95828a09b174d109033c4af10fdf2f65599e1c7365ca669dff3428e6e723462'


def load_helper(path):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != HELPER_SHA:
        raise RuntimeError('Reviewed profiling helper hash mismatch')
    source = raw.decode()
    for old, new, count in (
        ("'PYTHON_GIL'", "'PYTHON_ALL_THREADS'", 1),
        ("'python-gil.json'", "'python-threads.json'", 2),
        ("'python-gil.log'", "'python-threads.log'", 1),
        ('        import stationary_gate as G',
         "        import stationary_gate as G\n        G.UNITS = G.UNITS + ('atlas-voice-companion.service', 'atlas-safety-status.service')", 1),
    ):
        if source.count(old) != count:
            raise RuntimeError('Unexpected helper structure: ' + old)
        source = source.replace(old, new)
    module = types.ModuleType('atlas_localization_profile_helper')
    exec(compile(source, str(path), 'exec'), module.__dict__)
    original_command = module.python_command
    def all_thread_command(pid, output):
        command = original_command(pid, output)
        command.remove('--gil')
        return command
    module.python_command = all_thread_command
    return module


def configure(module):
    module.STAGE = STAGE
    module.TARGET_UNIT = 'atlas-localization-monitor.service'
    module.TARGET_SCRIPT = 'scripts/atlas_localization_monitor.py'
    module.HASHES = dict(module.HASHES, **{
        'scripts/atlas_localization_monitor.py': MONITOR_SHA,
        'scripts/atlas_localization_verify_core.py': CORE_SHA,
        'scripts/atlas_status_web.py': 'acb9fe18d384a7e2c06c24e1ab3abd5c3ebc1b46b5d26902ec39e1a3155d7439',
        'scripts/atlas_voice_companion.py': 'a88ff78df1ae2dded4f9984cdcf5e94d5335d1d12c77fd9c9131219725298870',
        'scripts/atlas_safety_status.py': '94f52bcc1d535378adf6d4f54f6d29fc52f0cd7b12b11a8da0df39117f510bd4',
    })
    return module


def main():
    if sys.argv[1:]:
        raise SystemExit('No arguments accepted: all CPU/RAM/temperature guards remain strict')
    module = configure(load_helper(Path(__file__).with_name('native_dashboard_cpu_once.py')))
    sys.argv = [sys.argv[0], '--python-gil'] # selects Python backend; wrapper removes GIL filter
    return module.main()


if __name__ == '__main__':
    sys.exit(main())
