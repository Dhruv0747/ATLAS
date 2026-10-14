"""Prepare exact Git-blob upgrade bytes; never installs or contacts production."""
import argparse, hashlib, json, pathlib, subprocess

COMMIT='04f9ad09025651e954d4e9bab03314a6a3700252'
PREFIX='project_atlas/tools/stage20_public/'
UNIT='.config/systemd/user/atlas-stage20-public-capture.service'
NAMES=('stage20_capture.py','stage20_production_gate.py','stage20_capture_integrity.py')
def digest(data):return hashlib.sha256(data).hexdigest()

def prepare(repo,baseline,out):
    repo=pathlib.Path(repo);baseline=pathlib.Path(baseline);out=pathlib.Path(out)
    out.mkdir(exist_ok=False,parents=True)
    files=[]
    mapping={PREFIX+'tools/diagnostics/'+n:'project_atlas/tools/diagnostics/'+n for n in NAMES}
    for target in (PREFIX+'atlas-stage20-public-capture.service',UNIT):
        mapping[target]='project_atlas/tools/diagnostics/stage20_public_capture.stationary30.service.in'
    for target,source in mapping.items():
        data=subprocess.check_output(['git','show',COMMIT+':'+source],cwd=repo)
        old=(baseline/target).read_bytes()
        p=out/target;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        files.append({'path':target,'before':digest(old),'after':digest(data),'source':source})
    manifest={'schema':1,'source_commit':COMMIT,'deployment_ready':True,
      'scope':'diagnostic_files_only','target_root':'/home/jetson',
      'installation_approval_required':True,'activation_authorized':False,
      'files':files,'unchanged_baseline':{str(p.relative_to(baseline)).replace('\\','/'):digest(p.read_bytes())
       for p in baseline.rglob('*') if p.is_file() and str(p.relative_to(baseline)).replace('\\','/') not in mapping}}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',required=True);p.add_argument('--baseline',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();print(json.dumps(prepare(a.repo,a.baseline,a.out),indent=2))
