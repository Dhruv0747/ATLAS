"""PC-only sysroot from complete reused ROS entries and signed ARM64 debs.

Never runs target package maintainer scripts or modifies host/Jetson packages.
"""
import hashlib
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT=Path('/root/atlas-stage29')


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--extend',action='store_true');args=parser.parse_args()
    target=ROOT/'target'
    manifest=ROOT/'cross-sysroot-manifest.json'
    if target.exists() and not args.extend:raise SystemExit('existing target preserved; incremental maintenance must be explicit')
    if args.extend:
        previous=json.loads(manifest.read_text());packages=previous['signed_repository_debs']
        known={x['file']:x['sha256'] for x in packages}
        for deb in sorted((ROOT/'apt/archives').glob('*.deb')):
            sha=digest(deb)
            if deb.name in known:
                if known[deb.name]!=sha:raise RuntimeError('cached dependency changed')
                continue
            info=subprocess.check_output(['dpkg-deb','-f',str(deb),'Package','Version','Architecture'],text=True)
            if 'Architecture: arm64' not in info and 'Architecture: all' not in info:raise RuntimeError('wrong target architecture')
            subprocess.run(['dpkg-deb','-x',str(deb),str(target)],check=True)
            packages.append({'file':deb.name,'sha256':sha,'metadata':info})
        for link in target.rglob('*'):
            if link.is_symlink() and str(link.readlink()).startswith('/') and not str(link.readlink()).startswith(str(target)+'/'):
                value=str(link.readlink());link.unlink();link.symlink_to(target/value.lstrip('/'))
                previous['relocated_absolute_links'].append({'path':str(link.relative_to(target)),'original_target':value})
        manifest.write_text(json.dumps(previous,indent=2));print('Extended private dependency set',len(packages));return
    archive=ROOT/'target-input.tar';reused=[];closed=False
    with tarfile.open(archive,mode='r:') as t:
        for m in t:
            if not m.name.startswith('opt/ros/humble'):
                if m.name.startswith('usr/include'):closed=True;break
                raise RuntimeError('unexpected prefix before complete ROS subtree')
            if m.isfile():
                f=ROOT/'sysroot'/m.name
                if not f.is_file() or f.stat().st_size!=m.size:raise RuntimeError('incomplete reused '+m.name)
                stream=t.extractfile(m);h=hashlib.sha256()
                for b in iter(lambda:stream.read(1024*1024),b''):h.update(b)
                if h.hexdigest()!=digest(f):raise RuntimeError('reused content mismatch '+m.name)
                reused.append({'path':m.name,'sha256':h.hexdigest(),'size':m.size})
    if not closed or not reused:raise RuntimeError('ROS subtree completeness not established')
    target.mkdir();(target/'opt/ros').mkdir(parents=True)
    shutil.copytree(ROOT/'sysroot/opt/ros/humble',target/'opt/ros/humble',symlinks=True)
    packages=[]
    for deb in sorted((ROOT/'apt/archives').glob('*.deb')):
        info=subprocess.check_output(['dpkg-deb','-f',str(deb),'Package','Version','Architecture'],text=True)
        if 'Architecture: arm64' not in info and 'Architecture: all' not in info:raise RuntimeError('wrong target architecture '+str(deb))
        subprocess.run(['dpkg-deb','-x',str(deb),str(target)],check=True)
        packages.append({'file':deb.name,'sha256':digest(deb),'metadata':info})
    if not packages:raise RuntimeError('no private dependency packages')
    changed=[]
    for link in target.rglob('*'):
        if link.is_symlink():
            value=str(link.readlink())
            if value.startswith('/'):
                link.unlink();link.symlink_to(target/value.lstrip('/'))
                changed.append({'path':str(link.relative_to(target)),'original_target':value})
    (ROOT/'cross-sysroot-manifest.json').write_text(json.dumps({
        'reused_ros_entries':reused,'signed_repository_debs':packages,
        'relocated_absolute_links':changed},indent=2))
    print('Complete ROS entries reused',len(reused),'ARM64/all debs extracted',len(packages))


if __name__=='__main__':main()
