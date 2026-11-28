"""PC-only versioned ARM64 runtime candidate; no install or activation."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT=Path('/root/atlas-stage29')
NAME='astra-arm64-stage29-v2'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    package=ROOT/NAME
    if package.exists():raise SystemExit('candidate already exists; preserve versioned evidence')
    shutil.copytree(ROOT/'cross-install',package,symlinks=False,
                    ignore=shutil.ignore_patterns('*x86_64*','__pycache__'))
    private=ROOT/'target/opt/ros/humble'
    for name in ('camera_info_manager','camera_calibration_parsers','image_publisher'):
        for f in (private/'lib').glob('lib'+name+'*'):
            if f.is_file():shutil.copy2(f,package/'lib'/f.name)
        source=private/'share'/name
        if source.exists():shutil.copytree(source,package/'share'/name)
    for pattern in ('libuvc.so*','libusb-1.0.so*'):
        for f in (ROOT/'target/usr/lib/aarch64-linux-gnu').glob(pattern):
            if f.is_file():shutil.copy2(f,package/'lib'/f.name)
    files=[];elf=[]
    for f in sorted(package.rglob('*')):
        if not f.is_file():continue
        raw=f.read_bytes()
        if raw[:4]==b'\x7fELF':
            if raw[4]!=2 or int.from_bytes(raw[18:20],'little')!=183:raise RuntimeError('non AArch64 ELF '+str(f))
            dynamic=subprocess.check_output(['aarch64-linux-gnu-readelf','-d',str(f)],text=True)
            if '(RPATH)' in dynamic or '(RUNPATH)' in dynamic:raise RuntimeError('unreviewed ELF runtime search path')
            elf.append({'path':str(f.relative_to(package)),'dynamic':dynamic})
        files.append({'path':str(f.relative_to(package)),'sha256':hashlib.sha256(raw).hexdigest(),'size':len(raw)})
    manifest={'source':'f7e71d9ce806e788cb48d8580aac2c778fba4214',
              'source_patch_sha256':digest(ROOT/'source-cross.patch'),'files':files,'elf':elf,
              'status':'CROSS BUILT; target loader and live streams NOT VERIFIED',
              'runtime':'Jetson only; PC is not required after installation'}
    (package/'manifest.json').write_text(json.dumps(manifest,indent=2))
    archive=ROOT/(NAME+'.tar.gz')
    with tarfile.open(archive,'w:gz') as tar:tar.add(package,arcname=NAME)
    print(json.dumps({'archive':str(archive),'sha256':digest(archive),'bytes':archive.stat().st_size,
                      'files':len(files),'AArch64_ELF':len(elf)},indent=2))


if __name__=='__main__':main()
