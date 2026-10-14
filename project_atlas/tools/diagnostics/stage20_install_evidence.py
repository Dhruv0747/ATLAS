"""Durable, sanitized installation evidence. No service or robot operations."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import traceback


def sanitize(value):
    if isinstance(value, dict):
        return {k: ('[REDACTED]' if re.search(r'password|passwd|token|secret|credential|pin\b', k, re.I)
                    else sanitize(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v) for v in value]
    if not isinstance(value, (str, bytes)):
        return value
    text = value.decode('utf-8', 'replace') if isinstance(value, bytes) else value
    text = re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----',
                  '[REDACTED KEY]', text, flags=re.S)
    text = re.sub(r'(?i)(https?://)[^/@\s]+:[^/@\s]+@', r'\1[REDACTED]@', text)
    text = re.sub(r'(?i)(bearer\s+)\S+', r'\1[REDACTED]', text)
    text = re.sub(r'(?i)(["\x27]?(?:password|passwd|token|secret|credential|pin)["\x27]?\s*[:=]\s*)'
                  r'("[^"]*"|\x27[^\x27]*\x27|[^\s,;]+)', r'\1[REDACTED]', text)
    return text


def file_state(paths):
    result = {}
    for path in paths:
        p = Path(path)
        if p.is_symlink():
            result[str(p)] = {'symlink': os.readlink(p)}
        elif p.is_file():
            result[str(p)] = {'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
        elif p.exists():
            result[str(p)] = {'directory': p.is_dir()}
        else:
            result[str(p)] = None
    return result


class Evidence:
    """Exclusive 0600 JSONL; inability to persist evidence aborts before action."""
    def __init__(self, path, identity, paths=()):
        self.path = Path(path)
        self.paths = list(paths)
        self.step = 'initialization'
        self.write_attempted = False
        self.rollback_attempted = False
        self.rollback_result = 'not_needed'
        self.failed_step = None
        self.before = file_state(self.paths)
        self.stream = os.fdopen(os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w')
        self.emit('begin', identity=identity, before=self.before)

    def emit(self, event, **data):
        record = sanitize(dict(timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                               event=event, step=self.step, **data))
        self.stream.write(json.dumps(record, sort_keys=True) + '\n')
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def phase(self, step, **data):
        if data.get('rollback_attempted') and self.failed_step is None:
            self.failed_step = self.step
        self.write_attempted |= bool(data.get('filesystem_write_attempted'))
        self.rollback_attempted |= bool(data.get('rollback_attempted'))
        if data.get('rollback_attempted'):
            self.rollback_result = 'pending'
        if 'rollback_result' in data:
            self.rollback_result = data['rollback_result']
        self.step = step
        self.emit('phase', **data)

    def runner(self, args):
        # Do not record arbitrary argv/environment; identity and named phase suffice.
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=30, check=False)
        except subprocess.TimeoutExpired as exc:
            self.emit('process_timeout', exit_code=None, stdout=exc.stdout, stderr=exc.stderr)
            raise
        self.emit('process_exit', exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
        if result.returncode:
            raise subprocess.CalledProcessError(result.returncode, args, result.stdout, result.stderr)
        return result

    def finish(self, error=None):
        try:
            after = file_state(self.paths)
            self.emit('failure' if error else 'success',
                      exit_code=getattr(error, 'returncode', 1 if error else 0),
                      exception_type=type(error).__name__ if error else None,
                      error=str(error) if error else None,
                      traceback=''.join(traceback.format_exception(type(error), error, error.__traceback__)) if error else None,
                      stdout=getattr(error, 'stdout', None), stderr=getattr(error, 'stderr', None),
                      after=after, net_target_change=after != self.before,
                      failing_step=(self.failed_step or self.step) if error else None,
                      filesystem_write_attempted=self.write_attempted,
                      rollback_attempted=self.rollback_attempted,rollback_result=self.rollback_result,
                      filesystem_change_note='Net target state only; phase events record transient writes and rollback.')
        finally:
            self.stream.close()
