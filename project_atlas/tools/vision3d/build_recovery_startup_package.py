"""PC-only package builder, no deployment or execution."""
import argparse,hashlib
from pathlib import Path
FILES=('recovery_startup_diagnostic.py','recovery_snapshot_runtime.py','recovery_attribution_trial.py','startup_cpu_attribution.py','snapshot_benchmark_once.py','stationary_gate.py','install_verification.py','restart_policy.py','atlas-recovery-startup-diagnostic.service')
def build(destination):
    destination=Path(destination);destination.mkdir(mode=0o700)
    for name in FILES:
        (destination/name).write_bytes((Path(__file__).parent/name).read_text(encoding='utf-8-sig').replace('\r\n','\n').encode())
    data=''.join(hashlib.sha256((destination/n).read_bytes()).hexdigest()+'  '+n+'\n' for n in FILES)
    (destination/'SHA256SUMS').write_bytes(data.encode());return hashlib.sha256(data.encode()).hexdigest()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('destination');args=p.parse_args();print(build(args.destination))
