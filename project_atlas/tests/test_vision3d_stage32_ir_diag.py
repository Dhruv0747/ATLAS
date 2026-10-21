"""Stage32 takeover: no-restart IR diagnostic package. Synthetic files only; no device, ROS, service or network."""
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / 'tools/vision3d'


def load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / (name + '.py'))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


B = load('stage32_ir_diag_package')
sha = lambda b: hashlib.sha256(b).hexdigest()


def fake_runtime(root, lib=b'BASELINE-LIB'):
    """458-file runtime whose manifest uses the real formatting; libastra_camera.so entry uses real baseline values."""
    files = []
    for i in range(457):
        p = root / ('lib/f%03d.so' % i); p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b'x%d' % i)
        files.append({'path': 'lib/f%03d.so' % i, 'sha256': sha(b'x%d' % i), 'size': len(b'x%d' % i)})
    (root / 'lib/libastra_camera.so').write_bytes(lib)
    files.insert(200, {'path': 'lib/libastra_camera.so', 'sha256': sha(lib), 'size': len(lib)})
    doc = {'source': 'f7e71d9', 'source_patch_sha256': 'p', 'files': files, 'elf': [], 'status': 's', 'runtime': 'r'}
    (root / 'manifest.json').write_text(json.dumps(doc, indent=2))
    return doc


class ManifestEdit(unittest.TestCase):
    def doc_text(self, sha_=B.LIB_BASE[0], size=B.LIB_BASE[1]):
        files = [{'path': 'lib/a.so', 'sha256': 'a' * 64, 'size': 1}] * 228 + [{'path': B.LIB, 'sha256': sha_, 'size': size}] \
            + [{'path': 'lib/b.so', 'sha256': 'b' * 64, 'size': 2}] * 229
        return json.dumps({'source': 's', 'files': files, 'elf': []}, indent=2)

    def test_changes_exactly_one_entry(self):
        t = self.doc_text(); out = B.edit_manifest(t)
        a, b = json.loads(t)['files'], json.loads(out)['files']
        changed = [i for i in range(len(a)) if a[i] != b[i]]
        self.assertEqual(changed, [228]); self.assertEqual(b[228], {'path': B.LIB, 'sha256': B.LIB_CAND[0], 'size': B.LIB_CAND[1]})
        self.assertEqual(len(out), len(t))   # same-length hex and 7-digit size: only those characters differ

    def test_refuses_unknown_baseline(self):
        with self.assertRaises(ValueError):
            B.edit_manifest(self.doc_text(sha_='c' * 64))

    def test_builder_refuses_wrong_archive(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'x.tar.gz'; p.write_bytes(b'not the candidate')
            with self.assertRaisesRegex(ValueError, 'archive hash'):
                B.build(p, p, Path(d) / 'out')


class Installer(unittest.TestCase):
    """Drives the real installer against a fake runtime with the payload hashes rewired to fake bytes."""
    def setUp(self):
        self.d = Path(tempfile.mkdtemp()); self.rt = self.d / 'runtime'; self.pkg = self.d / 'pkg'
        fake_runtime(self.rt)
        self.base_lib = (self.rt / 'lib/libastra_camera.so').read_bytes(); self.base_man = (self.rt / 'manifest.json').read_bytes()
        cand_lib = b'INSTRUMENTED-LIB-ATLAS_IR_COUNTERS'
        doc = json.loads(self.base_man)
        for f in doc['files']:
            if f['path'] == B.LIB:
                f.update(sha256=sha(cand_lib), size=len(cand_lib))
        cand_man = json.dumps(doc, indent=2).encode()
        (self.pkg / 'payload/lib').mkdir(parents=True)
        (self.pkg / 'payload/lib/libastra_camera.so').write_bytes(cand_lib); (self.pkg / 'payload/manifest.json').write_bytes(cand_man)
        meta = {'files': {B.LIB: {'baseline': sha(self.base_lib), 'candidate': sha(cand_lib)},
                          'manifest.json': {'baseline': sha(self.base_man), 'candidate': sha(cand_man)}}}
        (self.pkg / 'package.json').write_text(json.dumps(meta))
        shutil.copy2(TOOLS / 'stage32_ir_diag_install.py', self.pkg / 'stage32_ir_diag_install.py')
        self.env = dict(os.environ, ATLAS_IR_DIAG_RUNTIME=str(self.rt), ATLAS_IR_DIAG_STATE=str(self.d / 'state'),
                        ATLAS_IR_DIAG_SKIP_SAFETY='yes')

    def tearDown(self):
        shutil.rmtree(self.d)

    def run_cmd(self, cmd, approved=True):
        env = dict(self.env, OWNER_APPROVED='yes') if approved else self.env
        p = subprocess.run([sys.executable, str(self.pkg / 'stage32_ir_diag_install.py'), cmd], env=env, capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr

    def test_check_is_read_only(self):
        before = {p: p.read_bytes() for p in self.rt.rglob('*') if p.is_file()}
        rc, out = self.run_cmd('check', approved=False)
        self.assertEqual(rc, 0, out); self.assertIn('"integrity": "PASS"', out)
        self.assertEqual(before, {p: p.read_bytes() for p in self.rt.rglob('*') if p.is_file()})

    def test_refuses_without_approval(self):
        rc, out = self.run_cmd('apply', approved=False)
        self.assertNotEqual(rc, 0); self.assertIn('OWNER_APPROVED', out)
        self.assertEqual((self.rt / 'lib/libastra_camera.so').read_bytes(), self.base_lib)

    def test_apply_passes_worker_integrity_then_rollback_is_byte_identical(self):
        rc, out = self.run_cmd('apply'); self.assertEqual(rc, 0, out)
        r = json.loads(out); self.assertEqual(r['result'], 'APPLIED'); self.assertEqual(r['integrity_after'], 'PASS')
        self.assertFalse(r['restart']); self.assertFalse(r['camera_started'])
        rc, out = self.run_cmd('apply'); self.assertNotEqual(rc, 0)          # second apply refused
        rc, out = self.run_cmd('rollback'); self.assertEqual(rc, 0, out)
        self.assertEqual(json.loads(out)['integrity_after'], 'PASS')
        self.assertEqual((self.rt / 'lib/libastra_camera.so').read_bytes(), self.base_lib)
        self.assertEqual((self.rt / 'manifest.json').read_bytes(), self.base_man)

    def test_library_only_install_would_fail_worker_integrity(self):
        """Regression for the rolled-back candidate: replacing the library without the manifest blocks every Start."""
        shutil.copy2(self.pkg / 'payload/lib/libastra_camera.so', self.rt / 'lib/libastra_camera.so')
        spec = importlib.util.spec_from_file_location('inst', self.pkg / 'stage32_ir_diag_install.py')
        with patch.dict(os.environ, self.env):
            m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
            self.assertIn('integrity failure: lib/libastra_camera.so', m.integrity(self.rt))

    def test_failed_write_restores_baseline(self):
        (self.pkg / 'payload/manifest.json').write_bytes(b'{}')          # payload corrupted after packaging
        rc, out = self.run_cmd('apply'); self.assertNotEqual(rc, 0)
        self.assertIn('payload hash mismatch', out)
        self.assertEqual((self.rt / 'lib/libastra_camera.so').read_bytes(), self.base_lib)

    def test_mid_install_integrity_failure_restores(self):
        (self.rt / 'lib/f010.so').write_bytes(b'tampered')                 # unrelated runtime damage discovered after write
        doc = json.loads((self.rt / 'manifest.json').read_text())        # keep baseline manifest hash valid for refusal logic
        rc, out = self.run_cmd('apply')
        r = json.loads(out[out.index('{'):])
        self.assertEqual(r['result'], 'FAILED'); self.assertIn('f010', r['failure'])
        self.assertEqual((self.rt / 'lib/libastra_camera.so').read_bytes(), self.base_lib)
        self.assertEqual((self.rt / 'manifest.json').read_bytes(), self.base_man)

    def test_installer_never_restarts_or_starts_camera(self):
        import re
        src = (TOOLS / 'stage32_ir_diag_install.py').read_text()
        verbs = set(re.findall(r"'systemctl', '--user', '([a-z-]+)'", src))
        self.assertEqual(verbs, {'list-units', 'show'})            # read-only systemd queries only
        for forbidden in ('Popen(', 'os.system', '/api/vision3d/viewer', "'restart', '", '--ros-args'):
            self.assertNotIn(forbidden, src)
        self.assertEqual(src.count('subprocess.'), 2)

if __name__ == '__main__':
    unittest.main()


C = load('stage32_ir_boundary')
NAMES = ('created', 'started', 'publisher', 'wait_ok', 'wait_failed', 'ready', 'read_ok', 'read_failed', 'callback', 'converted',
         'publish_attempt', 'publish_returned', 'info_returned', 'exceptions')


def counters(final=1, subscribers=1, **kv):
    """Same text layout as ir_counters.hpp Counters::summary()."""
    v = dict({n: 0 for n in NAMES}, created=1, started=1, publisher=1, wait_ok=300, ready=300, read_ok=300, callback=300,
             converted=300, publish_attempt=300, publish_returned=300, info_returned=300)
    v.update({k: kv.pop(k) for k in list(kv) if k in v})
    rc = dict(create_rc=0, mode_rc=0, start_rc=0, wait_rc=0, read_rc=0, width=320, height=240, pixel_format=202, fps=30,
              stride=320, bytes=76800, frame_index=299, hardware_timestamp_us=1); rc.update(kv)
    return '[INFO] [1.0] [astra.astra_camera_node]: ATLAS_IR_COUNTERS final=%d ' % final + ' '.join(
        '%s=%s' % (n, v[n]) for n in NAMES) + ' ' + ' '.join('%s=%s' % kv for kv in rc.items()) + ' subscribers=%d' % subscribers


def session(rx=0, active=False, canvas=None):
    s = {'timeline': [{'streams': {'ir': {'rx': rx, 'rejected': 0, 'state': 'ACTIVE' if active else 'UNAVAILABLE'}}}]}
    if canvas: s['ir_canvas'] = canvas
    return s


class Boundary(unittest.TestCase):
    def verdict(self, line, sess=None):
        return C.classify(C.parse_driver(line), sess or session())['earliest_failed']

    def test_no_instrumentation_is_reported_not_guessed(self):
        self.assertEqual(self.verdict('set ir video mode 320x240'), 0)

    def test_device_never_ready_is_boundary_1(self):
        self.assertEqual(self.verdict(counters(wait_ok=0, wait_failed=10, ready=0, read_ok=0, callback=0, converted=0,
                                               publish_attempt=0, publish_returned=0, info_returned=0, wait_rc=102)), 1)

    def test_read_failure_is_boundary_1(self):
        self.assertEqual(self.verdict(counters(read_ok=0, read_failed=300, callback=0, converted=0, publish_attempt=0,
                                               publish_returned=0, read_rc=1)), 1)

    def test_empty_metadata_is_boundary_2(self):
        self.assertEqual(self.verdict(counters(bytes=0)), 2)

    def test_publish_exception_is_boundary_5(self):
        self.assertEqual(self.verdict(counters(publish_returned=0, exceptions=1)), 5)

    def test_no_subscriber_is_boundary_6(self):
        self.assertEqual(self.verdict(counters(subscribers=0)), 6)

    def test_matched_but_no_callback_is_boundary_7(self):
        self.assertEqual(self.verdict(counters()), 7)

    def test_api_and_canvas(self):
        self.assertEqual(self.verdict(counters(), session(rx=200, active=True)), 8)
        self.assertEqual(self.verdict(counters(), session(rx=200, active=True, canvas={'w': 320, 'min': 3, 'max': 3})), 9)
        self.assertIsNone(self.verdict(counters(), session(rx=200, active=True, canvas={'w': 320, 'min': 0, 'max': 255})))

    def test_installer_integrity_mirrors_worker_check(self):
        rt = (Path(__file__).resolve().parents[1] / 'scripts/atlas_vision3d_runtime.py').read_text()
        self.assertIn("if len(manifest['files'])!=458:raise ValueError('runtime manifest count mismatch')", rt)
        self.assertIn("hashlib.sha256(p.read_bytes()).hexdigest()!=f['sha256']", rt)
