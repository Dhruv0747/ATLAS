"""Read-only local-root summary; never starts/stops services or writes evidence."""
import hashlib
import json
from pathlib import Path
from statistics import mean

root=Path('/var/lib/atlas-monitoring-timestamp-retry-20261030')
for line in (root/'SHA256SUMS').read_text().splitlines():
    digest,name=line.split('  ',1)
    target=(root/name).resolve()
    assert root in target.parents,'invalid evidence path'
    assert hashlib.sha256(target.read_bytes()).hexdigest()==digest,'evidence checksum failed: '+name
samples=json.loads((root/'samples.json').read_text())
summary={'result':json.loads((root/'result.json').read_text()),'checksums':'PASS','phases':{}}
for phase in ('baseline','active'):
    rows=[s for s in samples if s.get('phase')==phase]
    if rows:
        summary['phases'][phase]={'samples':len(rows),**{key:{'average':mean(s[key] for s in rows),'peak':max(s[key] for s in rows)} for key in ('cpu','ram','temp')}}
print(json.dumps(summary,indent=2))
