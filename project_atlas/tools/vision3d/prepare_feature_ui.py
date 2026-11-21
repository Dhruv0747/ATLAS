"""Prepare one exact-live HTML insertion and verified inverse. Never deploys."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path

BASELINE='1511d33f060c450a3afc0c120711f1da18587f5f37f9e0796fad7d577bcddb48'
ITEMS=(
 ('Face Recognition','NOT INSTALLED','Identity model, opt-in enrollment and deletion backend not installed.'),
 ('Gesture Recognition','NOT INSTALLED','Validated gesture model and runtime not installed.'),
 ('Human Body Tracking','UNAVAILABLE','Person-box adapter prepared offline; no skeletal pose or real Astra verification.'),
 ('Target Tracking','UNAVAILABLE','Read-only 2D tracking adapter prepared offline; execution disabled. No servo commands.'),
 ('Object Detection','UNAVAILABLE','Existing Jetson TensorRT YOLO found; Astra adapter not deployed or physically verified.'),
 ('RGB-D 3D Mapping','UNAVAILABLE','Onboard candidate prepared; calibration, registration, TF and real geometry remain unverified.'))


def fragment():
    cards=''.join('<article class="afui-card"><h3>'+name+'</h3><strong>'+state+'</strong><p>'+reason+
        '</p><p>FPS / CPU / RAM / temperature / results: UNAVAILABLE</p><div>'+''.join(
        '<button type="button" class="btn" disabled>'+label+'</button>' for label in ('Start Test','Stop Test','Manual PASS','Manual FAIL'))+
        '</div></article>' for name,state,reason in ITEMS)
    return ('<!-- ATLAS-SIX-FEATURE-UI-BEGIN -->\n<style>\n'
        '#astraFeatureUi{display:block;padding:20px;margin:20px 0;max-width:100%;box-sizing:border-box}'
        '#astraFeatureUi .afui-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:16px}'
        '#astraFeatureUi .afui-card{min-width:0;padding:16px;border:1px solid rgba(255,255,255,.8);border-radius:20px;background:rgba(255,255,255,.65);box-shadow:0 4px 12px rgba(30,50,70,.07);overflow-wrap:anywhere}'
        '#astraFeatureUi h3{margin-top:0}#astraFeatureUi .btn{margin:4px 2px;opacity:.55;cursor:not-allowed}'
        '\n</style>\n<section id="astraFeatureUi" class="vl-state" aria-labelledby="afuiTitle">'
        '<h2 id="afuiTitle">Astra feature tests</h2><p>UI PREPARATION ONLY — feature execution is disabled.</p>'
        '<p>Implementation status reviewed 30 October 2026, candidate a5de48c. These are not live health readings. Existing camera controls and preview above remain unchanged.</p>'
        '<div class="afui-grid">'+cards+'</div>'
        '<p>No test is PHYSICALLY VERIFIED. Manual PASS requires a separately approved test with real sensor evidence.</p>'
        '<p>Face enrollment, identity deletion and pan/tilt following are unavailable. No face data is collected by this UI.</p>'
        '<p>The working distance preview is UNCALIBRATED — DIAGNOSTIC ONLY, not proof of accurate 3D mapping.</p>'
        '</section>\n<!-- ATLAS-SIX-FEATURE-UI-END -->\n').encode('utf-8')


def patch(raw):
    if hashlib.sha256(raw).hexdigest()!=BASELINE:raise ValueError('live baseline hash mismatch; do not overwrite')
    if raw.count(b'</main>')!=1:raise ValueError('ambiguous insertion anchor')
    return raw.replace(b'</main>',fragment()+b'</main>',1)


def inverse(raw):
    if raw.count(fragment())!=1:raise ValueError('candidate changed; manual review required')
    original=raw.replace(fragment(),b'',1)
    if hashlib.sha256(original).hexdigest()!=BASELINE:raise ValueError('rollback baseline mismatch')
    return original


def main():
    parser=argparse.ArgumentParser();parser.add_argument('baseline',type=Path);parser.add_argument('output',type=Path);a=parser.parse_args()
    original=a.baseline.read_bytes();candidate=patch(original)
    if inverse(candidate)!=original:raise ValueError('inverse verification failed')
    a.output.mkdir(parents=True,exist_ok=False)
    for name,raw in [('original.html',original),('candidate.html',candidate)]:
        (a.output/name).write_bytes(raw)
    delta=''.join(difflib.unified_diff(original.decode().splitlines(True),candidate.decode().splitlines(True),
                                    fromfile='web/v2/vision3d.html',tofile='web/v2/vision3d.html'))
    (a.output/'targeted.patch').write_bytes(delta.encode())
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in a.output.iterdir()}
    (a.output/'SHA256SUMS').write_bytes(''.join(v+'  '+k+'\n' for k,v in hashes.items()).encode())
    manifest=dict(deployment_authorized=False,files_changed=['web/v2/vision3d.html'],restart_required=False,
                  activation=False,hashes=hashes,rollback='restore original.html only after current candidate hash matches')
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(manifest))


if __name__=='__main__':main()
