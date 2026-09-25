"""Read-only capability audit over the existing web cache and evidence ledger.

NOT a controller, profile activator, physical validator or safety watchdog.
No ROS imports, background threads, network, serial, subprocess or writes.
The deterministic mux/base remain authoritative even if this report is absent.
"""
import json
import math
from pathlib import Path
import re
from atlas_ultrasonic_validity import ValidityWindow


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def entry(data, key):
    obj = data.get(key, {})
    return obj if isinstance(obj, dict) else {}


def fresh(data, key, limit):
    age = entry(data, key).get('age')
    return finite(age) and 0 <= age <= limit


def decoded(data, key):
    value = entry(data, key).get('value')
    try:
        value = json.loads(value) if isinstance(value, str) else value
    except (ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def load_registry(root):
    registry = json.loads((Path(root) / 'config/capability_registry.json').read_text(encoding='utf-8'))
    # Approval is deliberately not writable via this config in increment 1.
    if registry.get('schema_version') != 1 or registry.get('mode') != 'ADVISORY_ONLY' or registry.get('approved_profiles') != []:
        raise ValueError('Capability registry cannot authorize a motion profile')
    sensors = registry.get('sensors')
    if not isinstance(sensors, list) or not sensors or len({s['id'] for s in sensors}) != len(sensors):
        raise ValueError('Invalid capability source registry')
    if any(p.get('approval') not in ('NOT_VALIDATED', 'NOT_AVAILABLE') or p.get('max_speed_mps') != 0
           for p in registry.get('candidate_profiles', [])):
        raise ValueError('Candidate profile must remain disabled with zero speed authority')
    return registry


def encoder_transport(data):
    e = decoded(data, 'encoder_health')
    if not fresh(data, 'encoder_health', 1):
        return False, 'Shared encoder health missing/stale; not four independent failures'
    if e.get('packet_fresh') is not True or not finite(e.get('packet_age_s')) or not 0 <= e['packet_age_s'] <= 1:
        return False, 'Shared encoder packet invalid/stale'
    if e.get('state') not in ('READY', 'HEALTHY', 'DEGRADED', 'CRITICAL') or not isinstance(e.get('faults'), list):
        return False, 'Encoder owner not qualified or malformed health report'
    if e['state'] == 'CRITICAL' and not e['faults']:
        return False, 'Encoder owner reports unexplained critical state'
    selected = e.get('selected_encoders')
    excluded = e.get('excluded_encoders')
    # Require exactly the complement of zero or one explicitly excluded
    # channel. Two-encoder fallback is never accepted for navigation.
    if (not isinstance(selected, list) or not isinstance(excluded, list)
            or len(excluded) > 1
            or sorted(selected + excluded) != [1, 2, 3, 4]
            or set(selected) & set(excluded)
            or len(selected) < 3):
        return False, 'Unrecognized selected/excluded encoder policy'
    return True, 'Fresh shared packet; stationary counts are not a failure'


def sensor_health(sensor, data):
    check, key = sensor['check'], sensor.get('key')
    if check == 'unavailable':
        return 'NOT_AVAILABLE', 'No installed, physically validated VO/VIO source'
    if check == 'encoder':
        e = decoded(data, 'encoder_health')
        excluded = e.get('excluded_encoders')
        if fresh(data, 'encoder_health', 1) and isinstance(excluded, list) and sensor['channel'] in excluded:
            return 'EXCLUDED', 'Excluded feedback, not a disabled motor'
    if not fresh(data, key, sensor['max_age_s']):
        return 'STALE_OR_MISSING', 'No fresh source sample (negative/NaN ages are invalid)'
    value = entry(data, key).get('value')
    obj = value if isinstance(value, dict) else {}
    text = str(value)
    valid = False
    if check in ('encoder', 'wheel_odom'):
        good, reason = encoder_transport(data)
        if not good:
            return 'INVALID', reason
        e = decoded(data, 'encoder_health')
        if e['faults']:
            if check == 'wheel_odom':
                return 'DEGRADED', 'Owner reports selected fault(s): ' + str(e['faults'])[:200] + '; no approved alternate'
            channel = 'M' + str(sensor['channel'])
            if any(re.match(r'^' + channel + r'(?:\b|_)', str(f)) for f in e['faults']):
                return 'FAULT_REPORTED', 'Encoder owner evidence: ' + str(e['faults'])[:200] + '; cause not proven'
            # Unrecognized fault names must not falsely clear a selected channel.
            if any(not re.match(r'^M[1-4](?:\b|_)', str(f)) for f in e['faults']):
                return 'INVALID', 'Unclassified encoder-owner fault: ' + str(e['faults'])[:200]
        valid = finite(value) if check == 'encoder' else all(finite(obj.get(k)) for k in ('x', 'y', 'vx', 'wz'))
    elif check == 'finite':
        valid = finite(value)
    elif check == 'imu':
        valid = all(finite(obj.get(k)) for k in ('gx', 'gy', 'gz', 'ax', 'ay', 'az'))
    elif check == 'lidar':
        valid = all(finite(obj.get(k)) for k in ('points', 'total', 'nearest_m', 'range_max')) and 0 < obj['points'] <= obj['total'] and 0 < obj['nearest_m'] <= obj['range_max']
    elif check == 'camera':
        valid = finite(obj.get('bytes')) and obj['bytes'] > 0
    elif check == 'ultrasonic':
        if not fresh(data, 'us_validity', 1):
            return 'INVALID', 'Missing/stale UVALID1 sample proof; legacy ONLINE or range alone is insufficient'
        proof = decoded(data, 'us_validity')
        stamp = proof.get('host_monotonic_s')
        if not finite(stamp):
            return 'INVALID', 'Invalid sample envelope'
        # Read-only projection from cache age; persistent mux checks sequences
        # and same-host monotonic age independently. This grants no authority.
        window = ValidityWindow()
        window.ingest(proof, stamp + entry(data, 'us_validity')['age'])
        side = {'F': 'front', 'L': 'left', 'R': 'right', 'B': 'rear'}[sensor['code']]
        distance, state = window.reading(side, stamp + entry(data, 'us_validity')['age'])
        if state == 'DISABLED':
            return 'DISABLED', 'Channel disabled; not clearance'
        if state != 'VALID':
            return 'INVALID', 'Sample ' + state + '; not clearance'
        return 'DATA_PRESENT', f'Atomic MCU echo {distance:.3f} m; physical safety qualification still required'
    elif check == 'gps':
        gps = decoded(data, key)
        if gps.get('transport_open') is not True:
            return 'INVALID', 'GNSS transport not open'
        if not all(finite(gps.get(k)) and 0 <= gps[k] <= 2 for k in ('nmea_age_s', 'gga_age_s')):
            return 'INVALID', 'GNSS source sentences stale despite fresh dashboard report'
        if gps.get('fix_valid') is not True:
            return 'NO_FIX', 'NMEA communication present; no usable current position fix'
        valid = True
    elif check == 'radar':
        valid = bool(re.search(r'(?:^|[ ,;])state=VALID(?:$|[ ,;])', text))
    elif check == 'online':
        valid = text.startswith('online ')
    elif check == 'bme':
        valid = text.startswith('BME680_') and not any(w in text.upper() for w in ('OFFLINE', 'ERROR', 'FAIL'))
    elif check == 'ina':
        valid = text.startswith('INA3221_OK')
    elif check == 'bms':
        valid = decoded(data, key).get('ok') is True
    elif check == 'steering':
        steer = decoded(data, key)
        if steer.get('locked') is True:
            return 'LOCKED', 'Existing commissioning owner inhibits traction; no automatic release'
        valid = steer.get('locked') is False and steer.get('saving') is False and steer.get('error') == ''
    return ('DATA_PRESENT', 'Fresh plausible telemetry only; not physical validation') if valid else ('INVALID', 'Malformed/nonfinite/invalid value or unsupported source check')


def report(registry, records, data, goal_type='NAVIGATE_ROOM'):
    """Evaluate a goal scenario without dispatching, cancelling or resuming it."""
    # Even programmatic callers cannot grant authority through a forged registry.
    if registry.get('mode') != 'ADVISORY_ONLY' or registry.get('approved_profiles') != []:
        raise ValueError('Only an advisory registry is accepted')
    gates = {r['gate']: r for r in records}
    sensors = []
    for spec in registry['sensors']:
        health, reason = sensor_health(spec, data)
        missing = [g for g in spec['gates'] if gates.get(g, {}).get('status') != 'PASS']
        validation = ('NOT_VALIDATED' if missing else 'PASS_FOR_RECORDED_SCOPE_ONLY') if spec['gates'] else 'OBSERVATION_ONLY'
        if spec['check'] == 'unavailable':
            validation = 'NOT_AVAILABLE'
        raw_age = entry(data, spec.get('key')).get('age')
        sensors.append({**spec, 'health': health, 'reason': reason,
                        'age_s': raw_age if finite(raw_age) and raw_age >= 0 else None,
                        'validation': validation, 'missing_evidence': missing,
                        'motion_authority_granted': False})
    required = registry['goals'].get(goal_type)
    capabilities = []
    for name in required or []:
        sources = [s for s in sensors if name in s['capabilities']]
        if name == 'NEAR_FIELD_PROTECTION':
            sources = [s for s in sensors if s['check'] == 'ultrasonic']
        present = [s['id'] for s in sources if s['health'] == 'DATA_PRESENT']
        capabilities.append({'capability': name, 'configured_sources': [s['id'] for s in sources],
                             'observed_sources': present, 'validated_providers': [],
                             'state': 'OBSERVED_NOT_AUTHORIZED' if present else 'UNAVAILABLE_OR_UNQUALIFIED',
                             'reason': 'Directional components only, not full-body clearance or qualified protection' if name == 'NEAR_FIELD_PROTECTION'
                                       else 'No approved end-to-end profile; scope PASS is not motion authority'})
    policy = decoded(data, 'control_policy')
    restrictions = []
    if not fresh(data, 'control_policy', 1):
        restrictions.append('Control-policy report stale/missing')
    else:
        if policy.get('manual_only') is not False:
            restrictions.append('Manual-only gate active or unknown')
        if policy.get('stop_latched') is not False:
            restrictions.append('Emergency/remote stop latched or unknown')
    if not fresh(data, 'steering_calibration', 1) or decoded(data, 'steering_calibration').get('locked') is not False:
        restrictions.append('Steering lock active or state unknown')
    if not fresh(data, 'encoder_health', 1) or decoded(data, 'encoder_health').get('navigation_validated') is not True:
        restrictions.append('Encoder navigation validation absent or stale')
    agent = decoded(data, 'agent_state') if fresh(data, 'agent_state', 2) else {}
    live = agent.get('live', {})
    autonomy_age = live.get('autonomy_age_s') if isinstance(live, dict) else None
    autonomy = live.get('autonomy', {}) if finite(autonomy_age) and 0 <= autonomy_age <= 2 else {}
    goal = autonomy.get('goal') if isinstance(autonomy, dict) else None
    # Preserve text for display only; the agent may be absent or stale. Never
    # treat READY/ACTIVE in an agent summary as permission to drive.
    goal_text = str(goal)[:300] if goal is not None else 'UNKNOWN / no fresh goal report'
    return {'schema_version': 1, 'mode': 'ADVISORY_ONLY',
            'decision': 'NO_APPROVED_PROFILE' if required else 'UNKNOWN_GOAL_TYPE',
            'assessment_goal_type': goal_type, 'current_goal_report': goal_text,
            'goal_report_is_authoritative': False,
            'goal_retention': 'Unchanged in existing mission owner; automatic failure checkpoint/resume not implemented by this report',
            'motion_authorized': False, 'resume_authorized': False, 'max_speed_authorized_mps': 0,
            'active_profile': None, 'approved_profiles': [],
            'candidate_profiles': registry.get('candidate_profiles', []),
            'runtime_restrictions': restrictions, 'sensors': sensors, 'capabilities': capabilities,
            'reason': 'No physically approved fallback profile is registered. Restore/validate required capabilities; never replace wheel feedback with a camera image.',
            'scope': 'Read-only cached telemetry assessment, not a real-time safety loop or proof of every downstream consumer. Existing local safety remains authoritative.'}
