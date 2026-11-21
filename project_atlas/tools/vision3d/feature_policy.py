"""Offline feature admission model. Not a deployed pipeline launcher or safety guard.

The existing local safety guard must supervise every eventual runtime. This pure
function only describes admission; it cannot start cameras, inference or actuators.
"""
import math

FEATURES = ('mapping', 'obstacle_awareness', 'object_detection', 'target_tracking',
            'body_tracking', 'gesture_recognition', 'face_identification')
OPTIONAL = FEATURES[2:]


def decide(requested, available, safety, *, mapping_backlog=False, face_consent=False):
    result = dict(active=[], rejected={}, pan_tilt_allowed=False)
    try:
        valid = (safety['estop'] is True and safety['telemetry_fresh'] is True
                 and safety['stationary'] is True and safety['commands_zero'] is True)
        for key, limit in (('cpu', 75), ('ram', 80), ('temperature', 70)):
            value = safety[key]
            valid = valid and type(value) in (int, float) and math.isfinite(value) and 0 <= value < limit
    except (KeyError, TypeError):
        valid = False
    for name in requested:
        if name not in FEATURES:
            result['rejected'][name] = 'unknown feature'
        elif not valid:
            result['rejected'][name] = 'missing or unsafe stationary observation'
        elif available.get(name) is not True:
            result['rejected'][name] = 'dependency or input validation pending'
        elif name == 'face_identification' and face_consent is not True:
            result['rejected'][name] = 'explicit local face consent required'
        elif name in OPTIONAL and mapping_backlog:
            result['rejected'][name] = 'mapping/obstacle priority'
    for name in FEATURES:
        if name not in requested or name in result['rejected']:
            continue
        if name in OPTIONAL and any(x in OPTIONAL for x in result['active']):
            result['rejected'][name] = 'one optional pipeline budget; benchmark before concurrency'
        else:
            result['active'].append(name)
    return result
