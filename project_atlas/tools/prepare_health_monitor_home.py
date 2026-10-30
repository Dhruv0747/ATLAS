"""Prepare a two-insertion patch against an exact captured live homepage."""
import argparse
import hashlib
from pathlib import Path

def patch(live, template):
    if b'id="healthMonitorCard"' in live or b'/v2/health-monitor.js' in live:
        raise ValueError('already patched; do not repeat')
    start=template.index(b'  <details id="healthMonitorCard">')
    end=template.index(b'  </details>',start)+len(b'  </details>')
    fragment=template[start:end]+b'\n'
    anchor=b'  <a class="hm-lab" href="/v2/vision3d"'
    if live.count(anchor)!=1: raise ValueError('ambiguous Vision Lab anchor')
    position=live.index(b'\n',live.index(anchor))+1
    script=b'<script src="/v2/health-monitor.js" defer></script>\n'
    if live.count(b'</body>')!=1: raise ValueError('ambiguous body anchor')
    result=(live[:position]+fragment+live[position:]).replace(b'</body>',script+b'</body>')
    assert result.replace(fragment,b'',1).replace(script,b'',1)==live
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('live',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args()
    template=Path(__file__).resolve().parents[1]/'web/v2/index.html'
    data=patch(args.live.read_bytes(),template.read_bytes().replace(b'\r\n',b'\n'))
    with args.output.open('xb') as f:f.write(data)
    print(hashlib.sha256(data).hexdigest())
