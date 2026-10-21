"""PC/WSL package and rollback rehearsal. No SSH, install, restart or camera activation."""
import hashlib,json,pathlib,shutil,subprocess,sys,tarfile,tempfile
ROOT=pathlib.Path(__file__).resolve().parents[3]
LIB='lib/libastra_camera.so'
BASE={LIB:'6ae876010c824be97d2545996f897e40e07e0c97fa7a45694f96f342cf6e22a6',
 'project_atlas/scripts/atlas_vision3d_web.py':'889881c062717d076430414f57825b14f7f0de36ba4cf8c20b0c74fbff9ec1bf',
 'project_atlas/web/v2/vision3d.js':'76f9a20267e7d90a9d4b0a3be7f75a6c0e0ca594ddc1254e337e618215cf3fba'}
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
    out=pathlib.Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
    build=pathlib.Path('/root/atlas-stage29')
    candidate={LIB:(build/'cross-build/astra_camera/libastra_camera.so').read_bytes()}
    baseline={LIB:(build/'cross-install/lib/libastra_camera.so').read_bytes()}
    for f in BASE:
        if f==LIB:continue
        candidate[f]=(ROOT/f).read_bytes().replace(b'\r\n',b'\n')
        baseline[f]=subprocess.check_output(['git','show','d9e23bf:'+f],cwd=ROOT)
    manifest={'purpose':'IR diagnostic instrumentation; hardware root cause unresolved',
      'vendor_pin':'f7e71d9ce806e788cb48d8580aac2c778fba4214',
      'deployment_authorized':False,'activation_authorized':False,'files':{}}
    with tempfile.TemporaryDirectory() as tmp:
        t=pathlib.Path(tmp)
        for f,expected in BASE.items():
            assert sha(baseline[f])==expected,'baseline hash mismatch '+f
            payload=out/'payload'/f;payload.parent.mkdir(parents=True,exist_ok=True);payload.write_bytes(candidate[f])
            target=t/'target'/f;backup=t/'backup'/f
            target.parent.mkdir(parents=True,exist_ok=True);backup.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(baseline[f]);shutil.copy2(target,backup)
            shutil.copy2(payload,target);assert sha(target.read_bytes())==sha(candidate[f])
            shutil.copy2(backup,target);assert target.read_bytes()==baseline[f]
            manifest['files'][f]={'baseline':expected,'candidate':sha(candidate[f]),'bytes':len(candidate[f])}
    manifest['rollback_rehearsal']='PASS: all three restored byte-identically in isolated PC directory'
    # Preserve exact vendor delta; generated source diff contains no device data.
    diff=subprocess.check_output(['git','diff','--','astra_camera/src/ob_camera_node.cpp','astra_camera/include/astra_camera/ob_camera_node.h'],cwd=build/'source/ros2_astra_camera')
    (out/'vendor-instrumentation.diff').write_bytes(diff)
    manifest['vendor_diff_sha256']=sha(diff)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    with tarfile.open(out/'candidate.tar.gz','w:gz') as tar:
        tar.add(out/'payload',arcname='payload');tar.add(out/'manifest.json',arcname='manifest.json')
    print(json.dumps(manifest,indent=2));print('archive_sha256='+sha((out/'candidate.tar.gz').read_bytes()))
if __name__=='__main__':main()
