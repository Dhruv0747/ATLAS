"""Offline-testable deployment diagnostics; no hardware or service operations."""
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time


def redact(value):
    if isinstance(value, dict):
        return {k: ('[REDACTED]' if any(s in k.lower() for s in
                ('password', 'token', 'secret', 'credential', 'authorization', 'cookie'))
                else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        if value in ('STOPPED', 'NAV2', 'REMOTE', 'READY', 'LIVE'):
            return value
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            return {'redacted_text': True, 'length': len(value),
                    'sha256': hashlib.sha256(value.encode()).hexdigest()}
        if isinstance(parsed, (dict, list)):
            return redact(parsed)
        return '[REDACTED TEXT]'
    if isinstance(value, float) and not math.isfinite(value):
        return {'invalid_number': repr(value)}
    return value


def evaluate(data, api_error=None):
    checks = {}
    def check(name, ok, observed, reason):
        checks[name] = {'pass': bool(ok), 'observation': redact(observed),
                        'reason': 'accepted' if ok else reason}
    check('api', api_error is None, api_error, 'API unavailable or invalid JSON')
    ros = data.get('ros', {}) if isinstance(data, dict) else {}
    if not isinstance(ros, dict):
        ros = {}
    items = {}
    for name in ('control_policy', 'cmd_vel'):
        item = ros.get(name)
        check(name + '.present', isinstance(item, dict), item, 'missing or malformed observation')
        item = item if isinstance(item, dict) else {}
        age = item.get('age')
        check(name + '.fresh', type(age) in (int, float) and math.isfinite(age) and 0 <= age <= 1,
              age, 'age must be finite numeric and within 0..1 seconds')
        value = item.get('value')
        if name == 'control_policy' and isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                value = None
        check(name + '.value', isinstance(value, dict), value, 'missing or malformed value')
        items[name] = value if isinstance(value, dict) else {}
    policy, command = items['control_policy'], items['cmd_vel']
    for key, expected in [('stop_latched', True), ('manual_only', True), ('commission_armed', False)]:
        check(key, policy.get(key) is expected, policy.get(key), 'required boolean is ' + str(expected))
    check('source', policy.get('source') == 'STOPPED',
          {'is_stopped': policy.get('source') == 'STOPPED', 'raw': policy.get('source')}, 'source must be STOPPED')
    for key in ('lin', 'ang'):
        v = command.get(key)
        check('command.' + key, type(v) in (int, float) and v == 0, v, 'finite numeric zero required')
    return {'evaluation_unix': time.time(), 'evaluation_monotonic': time.monotonic(),
            'checks': checks, 'failed_predicates': [k for k, v in checks.items() if not v['pass']],
            'snapshot': redact(data), 'api_error_type': api_error}


def save(path, evidence):
    """Atomic private file with embedded payload digest and readback verification."""
    path = Path(path)
    payload = json.dumps(evidence, sort_keys=True, allow_nan=False).encode()
    digest = hashlib.sha256(payload).hexdigest()
    envelope = json.dumps({'sha256': digest, 'payload': evidence}, sort_keys=True, allow_nan=False).encode()
    fd, name = tempfile.mkstemp(prefix='.safety-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(envelope)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
        if os.name != 'nt':
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        saved = json.loads(path.read_bytes())
        actual = hashlib.sha256(json.dumps(saved['payload'], sort_keys=True, allow_nan=False).encode()).hexdigest()
        if actual != digest or saved['sha256'] != digest:
            raise OSError('safety evidence integrity verification failed')
        return digest
    finally:
        Path(name).unlink(missing_ok=True)
