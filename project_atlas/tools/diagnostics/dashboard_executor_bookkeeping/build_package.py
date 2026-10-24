"""Build the hash-pinned Dashboard executor ExitStack-removal package (offline; no SSH, deploy or restart).

usage: build_package.py <live_impl 543e4112...> <live_adapter 2b6ceeae...> <out_dir (must not exist)>
Package = V1 overlay + adapter whose ONLY change is OVERLAY_SHA, plus the two live originals for rollback."""
import hashlib, json, re, shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare_variants as P

LIVE_ADAPTER_SHA = '2b6ceeae09ec63cafd8a93084ba086c0e5145661f56a245966de4eed389f11ab'
WEB_SHA = 'acb9fe18d384a7e2c06c24e1ab3abd5c3ebc1b46b5d26902ec39e1a3155d7439'   # NOT modified; must stay installed
H = lambda b: hashlib.sha256(b).hexdigest()


def adapter_for(live_adapter: bytes, overlay_sha: str) -> bytes:
    if H(live_adapter) != LIVE_ADAPTER_SHA:
        raise SystemExit('live adapter hash mismatch')
    text = live_adapter.decode(); old = "OVERLAY_SHA = '%s'" % P.LIVE_SHA
    if text.count(old) != 1:
        raise SystemExit('adapter OVERLAY_SHA line not found exactly once')
    new = text.replace(old, "OVERLAY_SHA = '%s'" % overlay_sha)
    if new.replace(overlay_sha, P.LIVE_SHA) != text:
        raise SystemExit('adapter byte-exact reversal failed')
    return new.encode()


def build(live_impl: Path, live_adapter: Path, out: Path):
    impl_raw, adapter_raw = live_impl.read_bytes(), live_adapter.read_bytes()
    if H(impl_raw) != P.LIVE_SHA:
        raise SystemExit('live overlay hash mismatch')
    cand = P.v1(impl_raw.decode()).encode(); compile(cand, 'candidate', 'exec')
    adapter = adapter_for(adapter_raw, H(cand)); compile(adapter, 'adapter', 'exec')
    out.mkdir(parents=False, exist_ok=False); (out / 'install').mkdir(); (out / 'original').mkdir()
    (out / 'install/atlas_dashboard_executor_impl.py').write_bytes(cand)
    (out / 'install/atlas_dashboard_executor.py').write_bytes(adapter)
    (out / 'original/atlas_dashboard_executor_impl.py').write_bytes(impl_raw)
    (out / 'original/atlas_dashboard_executor.py').write_bytes(adapter_raw)
    shutil.copy(Path(__file__).with_name('dashboard_exitstack.sh'), out / 'dashboard_exitstack.sh')
    manifest = {'change': 'Dashboard executor overlay: per-cycle contextlib.ExitStack replaced by inline handle __enter__ + one LIFO exit block',
                'target_dir': '/home/jetson/project_atlas/scripts',
                'pre_sha256': {'atlas_dashboard_executor_impl.py': P.LIVE_SHA, 'atlas_dashboard_executor.py': LIVE_ADAPTER_SHA},
                'install_sha256': {'atlas_dashboard_executor_impl.py': H(cand), 'atlas_dashboard_executor.py': H(adapter)},
                'unchanged_required': {'atlas_status_web.py': WEB_SHA},
                'restart': 'rover-status-web only, separately approved; none performed by this builder', 'installed': False}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    files = sorted(p for p in out.rglob('*') if p.is_file() and p.name != 'SHA256SUMS')
    (out / 'SHA256SUMS').write_text(''.join('%s  %s\n' % (H(p.read_bytes()), p.relative_to(out)) for p in files))
    return manifest


if __name__ == '__main__':
    print(json.dumps(build(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])), indent=2))
