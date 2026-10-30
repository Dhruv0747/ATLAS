"""Prepare targeted candidates against the deployed static six-panel baseline.

No SSH/install/restart. Execution remains disabled in the packaged config.
"""
import argparse,hashlib,json,shutil,difflib
from pathlib import Path
from prepare_feature_ui import fragment
ROOT=Path(__file__).resolve().parents[2]
EXPECTED={'vision3d.html':'6d12362130e53fc6bb545ddba51100bf20a957e2f1ea7284a88ea9743c17ea57',
 'vision3d.js':'82d846cd09570d53ef984adc97bf51bed4be4d0ab629bf33b2386544e9d9084e',
 'atlas_vision3d_web.py':'2551d6578aa9429ac8f4fd5ff35f2c16a185c3cd027fafc563b7fff339857190'}


def candidates(baseline):
    original={name:(baseline/name).read_bytes() for name in EXPECTED}
    for name,data in original.items():
        if hashlib.sha256(data).hexdigest()!=EXPECTED[name]:raise ValueError('live baseline mismatch: '+name)
    html=(ROOT/'web/v2/vision3d.html').read_text()
    section=html[html.index(' <section class="vl-state" aria-labelledby="featureHeading">'):html.index('\n</main>')]
    section+='\n<link rel="stylesheet" href="/v2/vision_features.css">\n<script src="/v2/vision_features.js" defer></script>\n'
    if original['vision3d.html'].count(fragment())!=1:raise ValueError('missing static section')
    result={'vision3d.html':original['vision3d.html'].replace(fragment(),section.encode())}
    old=b"imageStamps[k] = response.headers.get('X-Source-Stamp'); urls[k] = URL.createObjectURL(blob); $(k + 'Image').src = urls[k];"
    new=old.replace(b"$(k + 'Image').src",b"$(k + 'Image').dataset.sourceStamp = imageStamps[k]; $(k + 'Image').src")
    if original['vision3d.js'].count(old)!=1:raise ValueError('RGB source-stamp anchor changed')
    result['vision3d.js']=original['vision3d.js'].replace(old,new)
    source=(ROOT/'scripts/atlas_vision3d_web.py').read_text()
    start=source.index("    if route in ('features','feature-report'):")
    end=source.index('\n    if post:',start)
    addition=source[start:end].encode()+b'\n'
    anchor=b"    route=p.path[len(API):];q=parse_qs(p.query)\n"
    if original['atlas_vision3d_web.py'].count(anchor)!=1:raise ValueError('API anchor changed')
    result['atlas_vision3d_web.py']=original['atlas_vision3d_web.py'].replace(anchor,anchor+addition)
    return original,result


def main():
    p=argparse.ArgumentParser();p.add_argument('baseline',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    old,new=candidates(a.baseline);a.output.mkdir(parents=True,exist_ok=False)
    for kind,files in [('rollback',old),('candidate',new)]:
        (a.output/kind).mkdir()
        for name,data in files.items():(a.output/kind/name).write_bytes(data)
    for name in old:
        diff=''.join(difflib.unified_diff(old[name].decode().splitlines(True),new[name].decode().splitlines(True),fromfile=name,tofile=name))
        (a.output/(name+'.patch')).write_bytes(diff.encode())
    for name in ['scripts/atlas_vision_feature_lab.py','scripts/atlas_vision_feature_worker.py','scripts/atlas_vision_features.py',
                 'scripts/atlas_vision_feature_guard.py','config/vision_feature_lab.json','web/v2/vision_features.js','web/v2/vision_features.css']:
        target=a.output/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    hashes={str(f.relative_to(a.output)).replace('\\','/'):hashlib.sha256(f.read_bytes()).hexdigest() for f in a.output.rglob('*') if f.is_file()}
    (a.output/'SHA256SUMS').write_bytes(''.join(h+'  '+n+'\n' for n,h in sorted(hashes.items())).encode())
    print(json.dumps(dict(files=len(hashes),manifest_sha256=hashlib.sha256((a.output/'SHA256SUMS').read_bytes()).hexdigest(),execution_enabled=False)))


if __name__=='__main__':main()
