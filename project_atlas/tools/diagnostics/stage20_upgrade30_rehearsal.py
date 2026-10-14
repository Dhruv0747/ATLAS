"""Native isolated exact-byte upgrade/rollback rehearsal. No service operations."""
import argparse, json, pathlib, shutil, tempfile, subprocess
from stage19_contract import require_isolation
from stage20_package_transaction import install,rollback
from stage20_install_guard import sha
from stage20_production_gate import verify_approval

def main():
    require_isolation()
    p=argparse.ArgumentParser();p.add_argument('--package',required=True);p.add_argument('--baseline',required=True)
    a=p.parse_args();pkg=pathlib.Path(a.package);base=pathlib.Path(a.baseline)
    m=json.loads((pkg/'manifest.json').read_text());results=[]
    # Entire write scope is newly created sandbox scratch, never the live home.
    for fail in (None,1,2,3,4,5):
        root=pathlib.Path(tempfile.mkdtemp(prefix='upgrade30-',dir='/tmp/replay'))
        shutil.copytree(base,root,dirs_exist_ok=True)
        sentinel=root/'project_atlas/data/diagnostics/existing-bag';sentinel.parent.mkdir(parents=True);sentinel.write_bytes(b'preserved evidence')
        original={str(f.relative_to(root)):sha(f) for f in root.rglob('*') if f.is_file()}
        try:
            r=install(m,pkg,root,owner_approved=True,fail_after=fail)
        except OSError:
            assert fail is not None
        else:
            assert fail is None
            assert all(sha(root/f['path'])==f['after'] for f in m['files'])
            unit=root/'.config/systemd/user/atlas-stage20-public-capture.service'
            s=unit.read_text();assert 'Restart=no' in s and '[Install]' not in s and '--stationary-30' in s
            subprocess.run(['systemd-analyze','--user','verify',str(unit)],check=True,capture_output=True)
            try:verify_approval(root/'no-grant.json',root/'project_atlas',stationary_30=True)
            except FileNotFoundError:pass
            else:raise AssertionError('missing grant accepted')
            rollback(r['backup'],root)
        assert all(sha(root/n)==h for n,h in original.items())
        assert list((root/'data/backups').glob('*/transaction.json'))
        results.append({'failure_after':fail,'exact_originals_restored':True,'history_preserved':True})
    print(json.dumps({'cases':results,'service_operations':[],'recording_started':False,'unit_parse':'passed','missing_grant':'refused','live_service_state':'not simulated; separately read-only verified'},indent=2))
if __name__=='__main__':main()
