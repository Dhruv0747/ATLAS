"""Read-only installation checks; no camera, ROS, service or control operations."""
import errno
import json
import time
import urllib.error
from pathlib import Path


def require_no_guard_failures(errors):
    if errors:
        raise ValueError('latched resource failure: ' + '; '.join(errors))


def wait_http_ready(fetch, independent_check, timeout=10, clock=time.monotonic,
                    sleep=time.sleep, events=None):
    """Only ECONNREFUSED is a bounded startup observation, never a safety PASS.

    fetch must have its own bounded timeout. independent_check must reject any
    latched resource failure and unknown ownership. Fresh full safety validation
    is required by the caller immediately after this returns.
    """
    events = events if events is not None else []
    deadline = clock() + timeout
    while True:
        independent_check()
        if clock() >= deadline:
            raise TimeoutError('HTTP readiness deadline expired')
        try:
            value = fetch()
        except urllib.error.URLError as exc:
            if not isinstance(exc.reason, OSError) or exc.reason.errno != errno.ECONNREFUSED:
                raise
            events.append({'mono': clock(), 'state': 'HTTP_UNAVAILABLE',
                           'safety': 'NOT_OBSERVED', 'reason': 'connection refused'})
        else:
            independent_check()
            if clock() >= deadline:
                raise TimeoutError('HTTP readiness response exceeded deadline')
            if not isinstance(value, dict) or not isinstance(value.get('ros'), dict):
                raise ValueError('malformed status response')
            return value
        sleep(min(.2, max(0, deadline-clock())))


def camera_processes(proc=Path('/proc')):
    """Inspect kernel process identity, not old runtime JSON or display text.

    Unreadable/ambiguous entries fail closed; vanished processes may be skipped.
    Covers the existing Astra executable, session worker and optional AI worker.
    """
    matches = []
    for p in proc.iterdir():
        if not p.name.isdigit():
            continue
        try:
            comm = (p/'comm').read_text().strip()
            args = (p/'cmdline').read_bytes().split(b'\0')
            names = [x.decode('utf-8', errors='strict').rsplit('/', 1)[-1] for x in args if x]
            if (comm in {'astra_camera_no', 'astra_camera_node', 'openni2_camera'} or
                any(n in {'astra_camera_node', 'openni2_camera_node', 'atlas_vision_feature_worker.py'} for n in names) or
                ('atlas_vision3d_runtime.py' in names and '--worker' in names)):
                matches.append({'pid': int(p.name), 'comm': comm})
        except FileNotFoundError:
            if p.exists():
                raise ValueError('incomplete process identity: '+p.name)
        except (OSError, UnicodeError) as exc:
            raise ValueError('unreadable process identity: '+p.name) from exc
    return matches


def verify_camera_off(fetch, inventory=camera_processes):
    before = inventory()
    summary = fetch()
    after = inventory()
    if before or after:
        raise ValueError('camera/inference process present')
    if not isinstance(summary, dict) or summary.get('state') != 'OFF':
        raise ValueError('camera state not OFF')
    if summary.get('driver_stopped') is not None and type(summary['driver_stopped']) is not bool:
        raise ValueError('invalid driver_stopped field')
    # A false flag is NOT converted to true: record the separate kernel evidence.
    return {'camera_state': 'OFF', 'reported_driver_stopped': summary.get('driver_stopped'),
            'process_inventory_before': before, 'process_inventory_after': after,
            'authority': 'OFF API plus two kernel process inventories',
            'driver_absence_verified': True}


def failure_record(primary, resource_errors, rollback_error=None):
    return {'error': str(primary), 'resource_guard_failures': list(resource_errors),
            'rollback_error': str(rollback_error) if rollback_error is not None else None}
