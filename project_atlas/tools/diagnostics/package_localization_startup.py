"""Prepare inert ARM64 startup bundle locally; never contacts the robot."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tarfile


def worker_source(source):
    replacements = {
        "CAPTURE = REPO / 'artifacts/localization_cpu_20261024/monitor.py'": "CAPTURE = REPO / 'monitor.py'",
        "if platform.machine().lower() not in ('x86_64', 'amd64'):":
        "if platform.machine().lower() != 'aarch64' or os.environ.get('ATLAS_STARTUP_SUPERVISED') != '1':",
        "raise RuntimeError('PC only')": "raise RuntimeError('Only supervised ARM64 worker permitted')",
        "    rows = []": "    rows = StageRows()",
        "        w, c = time.monotonic(), time.process_time()":
        "        w, c = time.monotonic(), time.process_time()\n        rows.append(dict(stage=name, event='BEGIN'))",
    }
    for old, new in replacements.items():
        if source.count(old) != 1:
            raise ValueError('Worker baseline changed: '+old)
        source = source.replace(old, new)
    pos = source.index('\ndef child(')
    helper = '''
class StageRows(list):
    def __init__(self):
        super().__init__()
        self.path = Path(os.environ['HOME']).parent / 'worker-stages.jsonl'
        self.file = self.path.open('x', buffering=1)
    def append(self, row):
        import resource
        row = dict(row, monotonic=time.monotonic(), native_tid=threading.get_native_id())
        row['rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        try:
            row['schedstat'] = Path('/proc/thread-self/schedstat').read_text().strip()
            row['cgroup'] = Path('/proc/self/cgroup').read_text().strip()
        except OSError:
            row['schedstat'] = 'UNKNOWN'
        # Counter location varies with cgroup v1/v2; do not guess attribution.
        row['cgroup_throttling'] = 'UNKNOWN: quota not reproduced'
        self.file.write(json.dumps(row)+'\\n'); self.file.flush()
        super().append(row)

'''
    source = source[:pos]+helper+source[pos:]
    # Reject parent mode: supervisor launches exactly one child, not a pair.
    source = source.replace("    if len(sys.argv) != 1:", "    raise ValueError('Worker requires --child original; no parent mode')\n    if len(sys.argv) != 1:")
    compile(source, '<prepared-worker>', 'exec')
    return source


def main():
    repo = Path(__file__).resolve().parents[3]
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=False)
    old = json.loads((repo/'artifacts/localization_arm64_cpu_report_20261024/manifest.json').read_text())
    files = {
        'localization_startup_jetson.py': repo/'project_atlas/tools/diagnostics/localization_startup_jetson.py',
        'monitor.py': repo/'artifacts/localization_cpu_20261024/monitor.py',
        'project_atlas/scripts/atlas_localization_monitor.py': repo/'artifacts/localization_cpu_20261024/monitor.py',
        'project_atlas/scripts/atlas_location_check_ros.py': repo/'artifacts/localization_cpu_20261024/manual.py',
        'project_atlas/scripts/atlas_localization_verify_core.py': repo/'artifacts/localization_core_live_20261024.py',
    }
    for name in ('atlas_background_search_budget.py','atlas_location_check_job.py'):
        files['project_atlas/scripts/'+name] = repo/'project_atlas/scripts'/name
    for name in ('atlas_latest.yaml','atlas_latest.pgm'):
        files['project_atlas/maps/'+name] = repo/'project_atlas/maps'/name
    for name, src in files.items():
        target = out/name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
    worker = out/'project_atlas/tools/diagnostics/startup_worker.py'
    worker.parent.mkdir(parents=True, exist_ok=True)
    worker.write_text(worker_source((repo/'project_atlas/tools/diagnostics/benchmark_localization_ros_startup.py').read_text()), encoding='utf-8')
    entries = {str(p.relative_to(out)).replace('\\','/'): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in out.rglob('*') if p.is_file()}
    manifest = out/'manifest.json'
    manifest.write_text(json.dumps(dict(package=entries, production=old['production'],
                                      approval='NOT APPROVED TO RUN', cpu_limit=75), indent=2)+'\n')
    archive = out.with_suffix('.tar.gz')
    if archive.exists(): raise FileExistsError(archive)
    with tarfile.open(archive, 'w:gz') as tar:
        for name in [*entries,'manifest.json']: tar.add(out/name, arcname=name)
    print(json.dumps(dict(archive=str(archive), sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                         manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(), files=len(entries))))


if __name__ == '__main__': main()
