"""Build a NEW offline directory only; no deploy, restart, SSH or ROS connection."""
import argparse
import hashlib
import json
from pathlib import Path
import benchmark_executor_counts as B

BASELINE = '98f3c2692e7c1c52e1285d3d91432ed521c67ff49c64508ad9a3813d1f0e5b79'
REPLACEMENTS = (
    ('import rclpy.executors\n',
     'import rclpy.executors\nfrom atlas_dashboard_executor import create_executor as _atlas_create_executor, spin as _atlas_spin\n'),
    ('executor = rclpy.executors.SingleThreadedExecutor()', 'executor = _atlas_create_executor()'),
    ('            rclpy.spin(self.node)', '            _atlas_spin(self.node)'),
)


def patch_web(raw):
    if hashlib.sha256(raw).hexdigest() != BASELINE:
        raise ValueError('live Dashboard baseline changed; abort')
    text = raw.decode()
    for old, new in REPLACEMENTS:
        if text.count(old) != 1:
            raise ValueError('ambiguous Dashboard patch')
        text = text.replace(old, new)
    compile(text, '<Dashboard-candidate>', 'exec')
    restored = text
    for old, new in reversed(REPLACEMENTS):
        restored = restored.replace(new, old)
    if restored.encode() != raw:
        raise ValueError('byte-perfect reversal failed')
    return text.encode()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('web', type=Path)
    p.add_argument('executor', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    web = a.web.read_bytes()
    overlay = B.cancellation_candidate(a.executor.read_bytes(), True).encode()
    adapter = Path(__file__).resolve().parents[2]/'scripts/atlas_dashboard_executor.py'
    payload = {'atlas_status_web.py': patch_web(web),
               'atlas_dashboard_executor.py': adapter.read_bytes(),
               'atlas_dashboard_executor_impl.py': overlay}
    for name, content in payload.items(): compile(content, name, 'exec')
    a.output.mkdir(exist_ok=False)
    for name, content in payload.items(): (a.output/name).write_bytes(content)
    (a.output/'atlas_status_web.original').write_bytes(web)
    manifest = dict(baseline_sha256=BASELINE, files={name: hashlib.sha256(data).hexdigest()
                    for name, data in payload.items()}, installed=False,
                    restart='NONE; separately approved rover-status-web restart required later')
    (a.output/'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__': main()
