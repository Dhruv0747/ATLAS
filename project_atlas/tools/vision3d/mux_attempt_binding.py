"""Per-attempt Mux binding (replaces the hard-coded sealed BINDING_SHA identity pin).

The sealed package's binding.json still pins publisher bytes and file metadata through the
reviewed manifest. Boot and process identity change on every boot or Mux restart, so they come
from one *per-attempt* snapshot instead. That snapshot is trusted only when:

- the owner approved its exact SHA256 out of band, passed at launch as ATLAS_MUX_ATTEMPT_SHA
  (a file is never trusted because its hash matches itself);
- it names the sealed package (archive and manifest SHA256);
- it is for the current boot and was captured recently on this boot;
- it lists exactly the sealed services, with unchanged unit hash, fragment path and Restart policy.

Live identity (PID plus /proc start ticks, NRestarts, drop-ins, dependencies, bytes and metadata)
is then re-checked against it by ServiceBinding and MuxFiles throughout the transaction.
This module never starts, stops or restarts anything.
"""
import hashlib
import json
import math
from pathlib import Path
import subprocess

SCHEMA = 'atlas-mux-attempt-binding/1'
MAX_AGE_S = 900.0           # snapshot must be taken within 15 min before the transaction starts
KEYS = {'schema', 'package', 'boot_id', 'captured_boottime', 'services'}
STATIC = ('ActiveState', 'FragmentPath', 'Restart', 'unit_sha256')
DYNAMIC = ('MainPID', 'start_ticks', 'NRestarts')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def approved_sha(value):
    """Validate the owner-supplied pin. Absent or malformed means no approval."""
    require(isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value),
            'attempt binding not owner-approved')
    return value


def strict_json(data):
    """Reject duplicate keys: the owner-reviewed bytes must mean exactly one thing."""
    def pairs(items):
        keys = [k for k, _ in items]
        require(len(keys) == len(set(keys)), 'attempt binding duplicate key')
        return dict(items)
    return json.loads(data, object_pairs_hook=pairs)


def canonical(binding):
    return json.dumps(binding, sort_keys=True, separators=(',', ':'), allow_nan=False).encode() + b'\n'


def load(data, approved, sealed, package, boot, now):
    """Return {boot_id, services, files} for ServiceBinding.check, or raise ValueError."""
    require(sha(data) == approved_sha(approved), 'attempt binding not owner-approved')
    b = strict_json(data)
    require(isinstance(b, dict) and set(b) == KEYS and b['schema'] == SCHEMA, 'attempt binding schema')
    require(b['package'] == package, 'attempt binding names a different package')
    require(b['boot_id'] == boot, 'reviewed boot identity changed')
    captured = b['captured_boottime']
    require(type(captured) in (int, float) and math.isfinite(captured) and 0 <= captured <= now
            and now - captured <= MAX_AGE_S, 'attempt binding stale or from the future')
    services = b['services']
    require(isinstance(services, dict) and set(services) == set(sealed['services']),
            'attempt binding service set differs from sealed package')
    for unit, row in services.items():
        reviewed = sealed['services'][unit]
        require(isinstance(row, dict) and set(row) == set(STATIC + DYNAMIC), 'attempt service schema: ' + unit)
        for key in STATIC:
            require(row[key] == reviewed[key], 'attempt service configuration drift: ' + unit + ' ' + key)
        require(row['ActiveState'] == 'active', 'attempt service not active: ' + unit)
        require(isinstance(row['MainPID'], str) and row['MainPID'].isdigit() and int(row['MainPID']) > 1,
                'attempt service PID invalid: ' + unit)
        require(type(row['start_ticks']) is int and row['start_ticks'] > 0, 'attempt start ticks invalid: ' + unit)
        require(isinstance(row['NRestarts'], str) and row['NRestarts'].isdigit(), 'attempt NRestarts invalid: ' + unit)
    return {'boot_id': b['boot_id'], 'services': services, 'files': sealed['files']}


def capture(sealed, package, boot, now, show=None, stat_reader=None):
    """Read-only snapshot of the live services named by the sealed package (operator tool)."""
    def default_show(unit):
        out = subprocess.check_output(['/usr/bin/systemctl', '--user', 'show', unit, '-p', 'MainPID',
                                       '-p', 'NRestarts', '-p', 'ActiveState', '-p', 'FragmentPath',
                                       '-p', 'Restart'], text=True, timeout=2)
        return dict(line.split('=', 1) for line in out.splitlines() if '=' in line)

    def default_stat(pid):
        text = Path('/proc', pid, 'stat').read_text()
        return int(text[text.rfind(')') + 2:].split()[19])

    show, stat_reader = show or default_show, stat_reader or default_stat
    services = {}
    for unit in sorted(sealed['services']):
        row = show(unit)
        services[unit] = {
            'MainPID': row['MainPID'], 'NRestarts': row['NRestarts'], 'ActiveState': row['ActiveState'],
            'FragmentPath': row['FragmentPath'], 'Restart': row['Restart'],
            'start_ticks': stat_reader(row['MainPID']),
            'unit_sha256': sha(Path(row['FragmentPath']).read_bytes()),
        }
    return canonical({'schema': SCHEMA, 'package': package, 'boot_id': boot,
                      'captured_boottime': now, 'services': services})
