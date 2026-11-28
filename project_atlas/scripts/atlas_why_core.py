"""Home "Why isn't ATLAS moving?" explainer (2026-11-28, owner: "dashboard more easy to understand").

Pure and read-only: it turns the mux policy (/atlas/control_policy), the mux safety text (/atlas/motion_safety) and the
mission-control status (/atlas/mission_status) into one plain-English line with a fix. It decides nothing and
authorises nothing; the mux, mission control and Nav2 keep every check.

level: 'stop' (something is stopping ATLAS now), 'wait' (a goal was refused: the owner must change something),
'ok' (driving / ready / manual), 'unknown' (no live data).
"""
import re

POLICY_MAX_AGE_S = 2.0       # the mux publishes its policy at 10 Hz
SAFETY_MAX_AGE_S = 1.5       # while blocked the mux repeats its reason every control cycle
MISSION_MAX_AGE_S = 5.0      # mission control repeats its current status at 1 Hz

# (pattern, title, fix). Order matters: more specific first.
SAFETY_RULES = [
    (r'LIDAR AVAILABILITY', 'The LiDAR cannot see part of the path, so the safety system holds ATLAS.',
     'Remove or cover dark, shiny or open areas next to the path (matte paper at LiDAR height helps), or start from '
     'a more open spot.'),
    (r'ULTRASONIC', 'An ultrasonic sensor is giving no data, so the safety system holds ATLAS.',
     'Check the ultrasonic sensor and its cable. The status card shows which one.'),
    (r'LOCALIZATION|LOCALISATION', 'ATLAS is not sure where it is on the map, so it will not drive.',
     'Keep ATLAS still for a few seconds or run Find my location, then try again.'),
    (r'ENCODER', 'The wheel sensors are not trusted right now, so ATLAS stops.',
     'Let ATLAS stand still; if it stays, check the Drive report card for the wheel at fault.'),
    (r'AUTONOMY BLOCKED: (FRONT|REAR|LEFT|RIGHT)', 'Something is too close to ATLAS, so it stops.',
     'Clear the way around ATLAS (about 0.3 m). It continues by itself once the way is clear.'),
    (r'RADAR LIMIT', 'A person or moving object is near, so ATLAS slows down.', 'Give ATLAS some room.'),
]
HEALTHY = ('AUTONOMY IDLE', 'ULTRASONIC DIRECTIONAL VETO: no veto', 'ULTRASONIC DISABLED', 'AUTONOMY DEGRADED')

MISSION_RULES = [
    (r'current pose is not in known clear space|candidate start is not clear',
     'ATLAS itself is standing too close to a wall or furniture on the map, so the goal was not started.',
     'Drive ATLAS by remote to open floor (about 0.5 m from walls and doors), then try again.'),
    (r'too close to a wall|occupied within|unknown within|(unknown|occupied) on the map',
     'The target point is too close to a wall or not free on the map, so the goal was refused.',
     'Pick a point in the open part of the room.'),
    (r'[Ll]ocali[sz]ation',
     'ATLAS is not sure where it is on the map, so the goal was refused.',
     'Keep ATLAS still for a few seconds or run Find my location, then try again.'),
    (r'camera obstacles', 'The obstacle camera is off or stale, so the goal was refused.',
     'Start the depth camera (Readiness page), then try again.'),
    (r'scan.*(agree|match)|SCAN CHECK FAIL', 'The LiDAR view does not match the map here, so the goal was refused.',
     'Check that nothing big was moved, then run Find my location.'),
]
_FINISHED = re.compile(r'^NAMED GOAL FINISHED name=(.+?) status=(\d+)')
_ACTIVE = re.compile(r'^(QUEUED navigate to |NAMED GOAL (?:DISPATCHED|ACCEPTED) name=)(.+)$')


def _out(level, title, detail='', fix='', source=''):
    return {'level': level, 'title': title, 'detail': detail, 'fix': fix, 'source': source}


def _match(rules, text):
    for pat, title, fix in rules:
        if re.search(pat, text or ''):
            return title, fix
    return None


def explain(policy, policy_age, safety, safety_age, mission, mission_age):
    if not isinstance(policy, dict) or policy_age is None or policy_age > POLICY_MAX_AGE_S:
        return _out('unknown', 'No live safety data from ATLAS.',
                    fix='Check that ATLAS is switched on and this page is connected.', source='dashboard')
    auto = policy.get('autonomy') or {}
    armed = bool(auto.get('armed'))
    if policy.get('stop_latched'):
        return _out('stop', 'E-STOP is on: ATLAS will not move.', detail=str(policy.get('stop_reason') or ''),
                    fix='Release it with the remote (sticks centred). Keep the remote in hand.', source='safety mux')
    safety = str(safety or '') if safety_age is not None and safety_age <= SAFETY_MAX_AGE_S else ''
    mission = str(mission or '') if mission_age is not None and mission_age <= MISSION_MAX_AGE_S else ''
    active = _ACTIVE.match(mission)
    if safety and not safety.startswith(HEALTHY) and not safety.startswith('REMOTE STOP'):
        hit = _match(SAFETY_RULES, safety)
        if hit:
            level = 'ok' if safety.startswith('RADAR LIMIT') else 'stop'
            return _out(level, hit[0], detail=safety, fix=hit[1], source='safety mux')
    fin = _FINISHED.match(mission)
    if fin:
        status = fin.group(2)
        if status == '4':
            return _out('ok', 'Arrived at %s.' % fin.group(1), source='mission control')
        if status == '6':
            return _out('wait', 'Navigation could not find a way to %s and stopped.' % fin.group(1), detail=mission,
                        fix='Clear the path or pick a nearer point, then try again.', source='mission control')
        return _out('ok', 'Goal %s was cancelled; ATLAS stopped.' % fin.group(1), detail=mission,
                    source='mission control')
    if mission.startswith(('ERROR', 'NAMED GOAL REJECTED', 'NAVIGATION STOPPED')):
        hit = _match(MISSION_RULES, mission) or ('The last goal was refused or stopped.',
                                                 'Read the detail below, fix it, then try again.')
        return _out('wait', hit[0], detail=mission, fix=hit[1], source='mission control')
    if active:
        if not armed:
            return _out('stop', 'Manual mode: a goal is waiting but ATLAS will not drive it.',
                        fix='Switch to Autonomous mode (operator PIN), or press Abort mission.', source='safety mux')
        note = 'Driving slower: a wheel sensor is degraded.' if safety.startswith('AUTONOMY DEGRADED') else ''
        return _out('ok', 'Driving to %s' % active.group(2), detail=note, source='mission control')
    if not armed:
        blockers = '; '.join(str(b) for b in auto.get('arm_blockers') or [])
        return _out('ok', 'Manual mode: ATLAS moves only with the remote or the drive pad.',
                    fix=('To send ATLAS somewhere: switch to Autonomous mode (' + blockers + ').') if blockers else
                    'To send ATLAS somewhere: switch to Autonomous mode (operator PIN).', source='safety mux')
    return _out('ok', 'Ready: Autonomous mode is on and ATLAS is waiting for a goal.',
                fix='Tap the map or press Go on a saved place.', source='mission control')
