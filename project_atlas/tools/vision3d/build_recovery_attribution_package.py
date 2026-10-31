"""Build PC-side passive-test package only; never deploys or runs it."""
import argparse
import hashlib
from pathlib import Path
FILES=('recovery_attribution_trial.py','startup_cpu_attribution.py','snapshot_benchmark_once.py','stationary_gate.py','install_verification.py','restart_policy.py')
def build(destination):
    destination=Path(destination);destination.mkdir(mode=0o700)
    for name in FILES:
        source=Path(__file__).parent/name
        (destination/name).write_bytes(source.read_text(encoding='utf-8-sig').replace('\r\n','\n').encode())
    raw=''.join(hashlib.sha256((destination/n).read_bytes()).hexdigest()+'  '+n+'\n' for n in FILES)
    (destination/'SHA256SUMS').write_text(raw,encoding='utf-8',newline='\n')
    return hashlib.sha256(raw.encode()).hexdigest()
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('destination');a=parser.parse_args();print(build(a.destination))
