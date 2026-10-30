"""Build a review package only. Never installs, activates or connects to Jetson."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
FILES=['config/onboard_mapping.json','scripts/atlas_map3d_web.py','web/v2/map3d.html','web/v2/map3d.js',
       'tools/vision3d/onboard_adapter.py','tools/vision3d/onboard_store.py','tools/vision3d/onboard_supervisor.py',
       'tools/vision3d/onboard_mapping.yaml','tools/vision3d/atlas-mapping-test.service.in',
       'tools/vision3d/calibration_validation.py','tools/vision3d/calibration_capture.py',
       'tools/vision3d/stationary_gate.py','tools/diagnostics/offboard_bridge_preflight.py']

def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    hashes={}
    for name in FILES:
        dst=a.output/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dst)
        hashes[name]=hashlib.sha256(dst.read_bytes()).hexdigest()
    (a.output/'SHA256SUMS').write_text(''.join(h+'  '+n+'\n' for n,h in hashes.items()))
    (a.output/'REVIEW_ONLY.json').write_text(json.dumps(dict(activation_allowed=False,files=hashes,
        dashboard_integration='Apply only targeted import, route and navigation changes against fresh live hashes; do not overwrite live homepage or web server',
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()),indent=2))
    print(json.dumps(dict(package=str(a.output),files=len(hashes),manifest_sha256=hashlib.sha256((a.output/'SHA256SUMS').read_bytes()).hexdigest())))

if __name__=='__main__':main()
