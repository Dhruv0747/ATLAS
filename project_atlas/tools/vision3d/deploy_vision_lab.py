"""Scoped Vision Lab package/install/rollback. Never starts camera or navigation.

Prepare on PC. Install on Jetson only after fresh safety/resource admission.
Only rover-status-web may restart. Backups include absent-file markers.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time

REPO=Path(__file__).resolve().parents[3]
LIVE=Path('/home/jetson/project_atlas')
BASELINES={
 'scripts/atlas_status_web.py':'fdd39477a19ee5ecde56c53e5e10e0d3f94fe074ae2830dd65e15851e93f30e1',
 'scripts/atlas_web_v2.py':'fa32d4574c82a21ef19af94d08c3eda120a543ee02a3eb86fcb172464e3c1f9e',
 'web/v2/index.html':'50c0040bad62ec3bacbada9f4d9c19e28af23cf0714edb280444eeea49778676'}
FILES=('scripts/atlas_vision3d_core.py','scripts/atlas_vision3d_web.py',
       'scripts/atlas_vision3d_runtime.py','web/v2/vision3d.html','web/v2/vision3d.css',
       'web/v2/vision3d.js','config/vision3d_live.json','tools/vision3d/stationary_gate.py',
       'tools/vision3d/stationary_ros_probe.py')


def sha(raw):return hashlib.sha256(raw).hexdigest()


def patch_baseline(rel,raw):
    text=raw.decode()
    if rel=='scripts/atlas_status_web.py':
        patches=[('import atlas_flysky_web   # FlySky Remote Test Lab (additive; read-only, lazy subscriber, no publishers)',
                  'import atlas_flysky_web   # FlySky Remote Test Lab (additive; read-only, lazy subscriber, no publishers)\nimport atlas_vision3d_web  # Isolated read-only Vision Lab'),
                 ('        if atlas_web_v2.handles(self.path):',
                  '        if atlas_vision3d_web.serve(self):\n            return\n        if atlas_web_v2.handles(self.path):'),
                 ("        if self.path == '/api/estop/reset':",
                  "        if atlas_vision3d_web.serve(self, post=True):\n            return\n        if self.path == '/api/estop/reset':")]
    elif rel=='scripts/atlas_web_v2.py':
        patches=[("'flysky-testlab': 'flysky-testlab.html'}", "'flysky-testlab': 'flysky-testlab.html', 'vision3d': 'vision3d.html'}")]
    elif rel=='web/v2/index.html':
        patches=[('  <nav class="nav" aria-label="Pages">',
                  '  <nav class="nav" aria-label="Pages">\n    <a class="btn ghost" href="/v2/vision3d">3D Vision Lab</a>')]
    else:raise ValueError('unapproved patch target')
    for old,new in patches:
        if text.count(old)!=1:raise ValueError('patch anchor mismatch '+rel)
        text=text.replace(old,new,1)
    if rel.endswith('.py'):compile(text,rel,'exec')
    return text.encode()


def prepare(destination):
    if destination.exists():raise ValueError('preserve existing package')
    payload={rel:(REPO/'project_atlas'/rel).read_bytes() for rel in FILES}
    # Exact live baseline copied read-only; don't deploy unrelated repository hooks.
    prior=REPO/'artifacts/astra_stationary_20261021'
    for rel,name in zip(BASELINES,('web_deploy_baseline.py','web_v2_deploy_baseline.py','home_deploy_baseline.html')):
        raw=(prior/name).read_bytes()
        if sha(raw)!=BASELINES[rel]:raise ValueError('baseline integrity failed '+rel)
        payload[rel]=patch_baseline(rel,raw)
    manifest={'baseline':BASELINES,'files':{r:sha(b) for r,b in payload.items()},
              'restart_only':'rover-status-web.service','camera_autostart':False,
              'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()}
    import io
    with tarfile.open(destination,'w:gz') as tar:
        for rel,raw in {**payload,'deployment-manifest.json':json.dumps(manifest,indent=2).encode()}.items():
            entry=tarfile.TarInfo(rel);entry.size=len(raw);entry.mode=0o644;tar.addfile(entry,io.BytesIO(raw))
    print(json.dumps({'archive':str(destination),'sha256':sha(destination.read_bytes()),'files':len(payload)}))


def verified_payload(package,expected):
    if sha(package.read_bytes())!=expected:raise ValueError('package hash mismatch')
    with tarfile.open(package) as tar:
        members=tar.getmembers()
        if any(not m.isfile() or m.size>2*1024**2 or Path(m.name).is_absolute() or '..' in Path(m.name).parts for m in members):
            raise ValueError('unsafe package member')
        payload={m.name:tar.extractfile(m).read() for m in members}
    manifest=json.loads(payload.pop('deployment-manifest.json'))
    if set(payload)!=set(FILES)|set(BASELINES) or len(members)!=len(payload)+1:raise ValueError('package allowlist mismatch')
    if manifest['baseline']!=BASELINES or manifest['files']!={k:sha(v) for k,v in payload.items()}:raise ValueError('payload manifest mismatch')
    for rel,raw in payload.items():
        if rel.endswith('.py'):compile(raw,rel,'exec')
    return payload,manifest


def restore(root,backup,ledger):
    for rel,row in ledger.items():
        target=root/rel
        if row['existed']:
            raw=(backup/rel).read_bytes()
            if sha(raw)!=row['sha256']:raise ValueError('rollback backup corrupt')
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        elif target.exists():target.unlink()  # Only enumerated new deployment files.


def rehearsal(root,backup,payload):
    """Private fixture: install candidate then restore and verify exact old tree."""
    root.mkdir();backup.mkdir();ledger={}
    for rel,raw in payload.items():
        target=root/rel;target.parent.mkdir(parents=True,exist_ok=True)
        if rel in BASELINES:target.write_bytes(b'prior fixture\n')
        existed=target.exists();prior=target.read_bytes() if existed else None
        ledger[rel]={'existed':existed,'sha256':sha(prior) if existed else None}
        if existed:
            old=backup/rel;old.parent.mkdir(parents=True,exist_ok=True);old.write_bytes(prior)
        target.write_bytes(raw)
    restore(root,backup,ledger)
    if any((root/rel).exists()!=row['existed'] or row['existed'] and sha((root/rel).read_bytes())!=row['sha256'] for rel,row in ledger.items()):
        raise ValueError('rollback rehearsal failed')


def install(package,expected):
    payload,manifest=verified_payload(package,expected)
    sys.path.insert(0,'/home/jetson/project-atlas-migration/astra-20261021')
    import stationary_gate as G
    import stationary_ros_probe as P
    rows,units=G.preflight();P.extra_safety()
    runtime=Path('/home/jetson/project-atlas-migration/astra-20261021/astra-arm64-stage29-v2')
    for f in json.loads((runtime/'manifest.json').read_text())['files']:
        if sha((runtime/f['path']).read_bytes())!=f['sha256']:raise ValueError('Astra runtime integrity failed')
    if shutil.disk_usage(LIVE).free<1024**3:raise ValueError('less than1GiB free')
    for rel in FILES:
        if (LIVE/rel).exists():raise ValueError('new target already exists; preserve '+rel)
    for rel,expected_hash in BASELINES.items():
        if sha((LIVE/rel).read_bytes())!=expected_hash:raise ValueError('live baseline changed '+rel)
    base=Path('/home/jetson/project-atlas-migration')/('vision3d-deploy-'+time.strftime('%Y%m%d-%H%M%S'))
    base.mkdir()
    rehearsal(base/'rehearsal',base/'rehearsal-backup',payload)
    backup=base/'backup';backup.mkdir();ledger={}
    for rel in payload:
        p=LIVE/rel;prior=p.read_bytes() if p.exists() else None
        ledger[rel]={'existed':prior is not None,'sha256':sha(prior) if prior is not None else None}
        if prior is not None:
            old=backup/rel;old.parent.mkdir(parents=True,exist_ok=True);old.write_bytes(prior)
    (base/'rollback-ledger.json').write_text(json.dumps(ledger,indent=2))
    (base/'manifest.json').write_text(json.dumps(manifest,indent=2))
    before_web=subprocess.check_output(['systemctl','--user','show','rover-status-web.service','-p','MainPID','-p','NRestarts'],text=True)
    result={'backup':str(backup),'rollback':str(base/'rollback-ledger.json'),'preflight':rows,'units_before':units,'web_before':before_web}
    try:
        for rel,raw in payload.items():
            p=LIVE/rel;p.parent.mkdir(parents=True,exist_ok=True)
            temp=p.with_suffix(p.suffix+'.vision3d-new');temp.write_bytes(raw);temp.replace(p)
        if any(sha((LIVE/r).read_bytes())!=h for r,h in manifest['files'].items()):raise ValueError('installed hash mismatch')
        subprocess.run(['systemctl','--user','restart','rover-status-web.service'],check=True,timeout=20)
        import urllib.request
        for _ in range(15):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8088/v2/vision3d',timeout=2) as reply:
                    if reply.status==200:break
            except OSError:time.sleep(1)
        else:raise ValueError('Vision Lab unavailable after restart')
        if G.services()!=units:raise ValueError('protected production service changed')
        result.update(result='INSTALLED',hashes=manifest['files'],units_after=G.services(),
                      web_after=subprocess.check_output(['systemctl','--user','show','rover-status-web.service','-p','MainPID','-p','NRestarts'],text=True))
    except Exception as e:
        restore(LIVE,backup,ledger)
        subprocess.run(['systemctl','--user','restart','rover-status-web.service'],check=True,timeout=20)
        result.update(result='ROLLED BACK',failure=str(e))
        raise
    finally:
        (base/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepare',type=Path);p.add_argument('--install',type=Path);p.add_argument('--sha256');a=p.parse_args()
    if a.prepare:prepare(a.prepare)
    elif a.install and a.sha256:install(a.install,a.sha256)
    else:raise SystemExit('explicit package preparation or guarded installation required')
