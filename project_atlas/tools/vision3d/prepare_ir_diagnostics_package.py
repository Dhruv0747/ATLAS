"""Prepare/rehearse a TWO-FILE diagnostics-only candidate on PC; never deploys."""
import hashlib,json,shutil,subprocess,sys,tarfile,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
FILES={'scripts/atlas_vision3d_web.py':'889881c062717d076430414f57825b14f7f0de36ba4cf8c20b0c74fbff9ec1bf',
       'web/v2/vision3d.js':'76f9a20267e7d90a9d4b0a3be7f75a6c0e0ca594ddc1254e337e618215cf3fba'}
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
    out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
    manifest={'purpose':'diagnostic/status correction ONLY; IR delivery root cause unresolved',
              'deployment_authorized':False,'restart_required':'rover-status-web only, separate approval',
              'files':{}}
    with tempfile.TemporaryDirectory() as tmp:
        target=Path(tmp)/'target';backup=Path(tmp)/'backup'
        for f,expected in FILES.items():
            original=subprocess.check_output(['git','show','d9e23bf:project_atlas/'+f],cwd=ROOT)
            assert sha(original)==expected,'baseline mismatch'
            new=(ROOT/'project_atlas'/f).read_bytes()
            # Package canonical LF to agree with Git and Linux installed hashes.
            new=new.replace(b'\r\n',b'\n')
            for root,body in ((target,original),(backup,original),(out/'project_atlas',new)):
                p=root/f;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(body)
            shutil.copy2(out/'project_atlas'/f,target/f)
            assert sha((target/f).read_bytes())==sha(new)
            shutil.copy2(backup/f,target/f)
            assert (target/f).read_bytes()==original
            manifest['files'][f]={'before_sha256':expected,'candidate_sha256':sha(new)}
    manifest['offline_apply_restore']='PASS: byte-identical rollback of both files in temporary tree'
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    with tarfile.open(out/'candidate.tar.gz','w:gz') as tar:
        tar.add(out/'manifest.json',arcname='manifest.json')
        for f in FILES:tar.add(out/'project_atlas'/f,arcname='project_atlas/'+f)
    print(json.dumps({'manifest':manifest,'archive_sha256':sha((out/'candidate.tar.gz').read_bytes())},indent=2))
if __name__=='__main__':main()
