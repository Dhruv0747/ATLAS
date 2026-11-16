"""Autonomy readiness checklist (2026-11-15, owner: "tell me why autonomy won't move, how to clear it, open the test
page, and unlock by itself when the test passes — no developer needed"). Pure; the web layer collects the inputs.

Every item: id, ok, title, why (current reason), steps (what to physically do), action (button: page link or API
call) and unlocks_by (what clears it). Items that the owner cannot fix from the dashboard say so plainly.
Owner decision 2026-11-15 ("Owner sign-off test"): there is NO override for safety items (mux, speed, encoders,
E-STOP, localization, camera); each is cleared only by its owner-run test/check. Only 'waypoints' is optional.
2026-11-16 owner: "use English in the dashboard, no Hindi" — all dashboard text is English (voice stays Hindi).
"""

LOC_FRESH_S = 120.0
# 2026-11-15 owner: "LiDAR confirm takes long while the estimate is right". Mission control itself uses AMCL + a 1 s
# scan check per goal; the dashboard now also accepts a confident AMCL estimate after a recent LiDAR VERIFIED.
AMCL_MAX_XY_STD_M = 0.15
AMCL_MAX_YAW_STD_DEG = 10.0
AMCL_MAX_AGE_S = 3.0
VERIFIED_WITHIN_S = 30 * 60.0


def _fmt(t):
    return f'{t:.2f} m/s'


def amcl_confident(amcl, amcl_age_s):
    a = amcl or {}
    try:
        return (amcl_age_s is not None and 0 <= amcl_age_s <= AMCL_MAX_AGE_S and not a.get('uncertain')
                and not a.get('large_step') and float(a.get('xy_std_m', 9)) <= AMCL_MAX_XY_STD_M
                and float(a.get('yaw_std_deg', 999)) <= AMCL_MAX_YAW_STD_DEG
                and (a.get('recent_jump_s') is None or float(a['recent_jump_s']) > 30.0))
    except (TypeError, ValueError):
        return False


def checklist(policy, encoder_health, encoder_age_s, loc_check, loc_age_s, astra_age_s, bridge_active,
              speed_ev, gate, places_count, speed_check_running=False, amcl=None, amcl_age_s=None,
              last_verified_age_s=None):
    items = []
    auto = (policy or {}).get('autonomy') or {}
    latched = (policy or {}).get('stop_latched')

    def add(id_, ok, title, why, steps, action=None, unlocks_by=''):
        items.append({'id': id_, 'ok': bool(ok), 'title': title, 'why': why if not ok else '',
                      'steps': steps if not ok else [], 'action': action if not ok else None,
                      'unlocks_by': unlocks_by})

    # 1. mux link
    add('mux', policy is not None, 'Safety controller (mux) online',
        'The dashboard is not receiving fresh status from the mux.',
        ['Check that the rover is powered and connected to Wi-Fi.', 'Wait 30 seconds and refresh the page.',
         'If it still does not come back, restart the rover.'], None,
        'Automatically, as soon as fresh mux status arrives.')

    # 2. speed (closed loop + owner-run ground check)
    enabled = bool((speed_ev or {}).get('enabled'))
    missing = (speed_ev or {}).get('missing', [])
    latest = (speed_ev or {}).get('latest', {})
    fails = []
    for t, r in sorted(latest.items()):
        if r.get('verdict') != 'PASS' and r.get('fresh'):
            fails.append(f"{_fmt(float(t))}: FAIL ({', '.join(r.get('failed_checks') or [r.get('end_reason') or '?'])})")
    if not enabled:
        why = 'Closed-loop speed control is off, so the rover does not drive at the commanded speed.'
        steps = ['This setting is enabled by a developer deploy (config/speed_loop.yaml).',
                 'After it is enabled, run the Speed check below.']
    else:
        need = int((speed_ev or {}).get('passes_needed', 1))
        have = len([t for t in (speed_ev or {}).get('passed', []) if t in missing])
        why = (f'Speed check pending: {have}/{need} PASS at {", ".join(_fmt(t) for t in missing)}'
               + (' • last: ' + '; '.join(fails) if fails else ''))
        steps = ['Place the rover in open space: at least 1.5 m clear ahead, nothing within 0.6 m.',
                 'Hold the remote with sticks centred; release the E-STOP (B).',
                 'On the Readiness page enter the PIN and press "Speed check". The rover drives ~0.6 m slowly and '
                 'stops by itself.',
                 'Bring the rover back and run "Speed check" once more (2 PASS needed).',
                 'After two PASS this blocker clears by itself. If anything looks wrong, press B.']
    add('speed', bool(gate.get('speed_validated')), 'Speed verified (commanded = actual)', why, steps,
        {'label': 'Open Speed check', 'href': '/v2/readiness#speed'} if enabled else None,
        'Automatically after 2 PASS (any config or code change needs a new check).')

    # 3. encoders
    enc_ok = encoder_age_s is not None and 0 <= encoder_age_s <= 2 and bool((encoder_health or {}).get('autonomy_ready'))
    if encoder_age_s is None or not 0 <= encoder_age_s <= 2:
        ewhy = 'No data from the wheel encoders.'
    elif not (encoder_health or {}).get('navigation_validated'):
        ewhy = 'Encoders are not yet validated for autonomy (ground round-trip check pending).'
    else:
        ewhy = f"Encoder state: {(encoder_health or {}).get('state', '?')} — {(encoder_health or {}).get('reason', '')}"
    add('encoders', enc_ok, 'Wheel encoders ready', ewhy,
        ['Open the Motor & Encoder Test Lab and watch all four wheel counts (rover lifted or standing still).',
         'If a wheel counts 0 or backwards, check its wire/connector.',
         'If the wiring is fine but it is still blocked, contact the developer.'],
        {'label': 'Motor & Encoder Test Lab', 'href': '/v2/testlab'}, 'Automatically when encoder health is OK.')

    # 4. E-STOP latched to switch ON
    add('estop', bool(latched) or auto.get('armed'), 'E-STOP latched (to switch ON)',
        'To switch Autonomous mode on, the rover must first be stopped (E-STOP latched).',
        ['Press B on the remote.', 'Then enter the PIN and press "Autonomous mode".',
         'Then release the E-STOP from the remote (sticks centred, press and release LB).'],
        None, 'As soon as B is pressed.')

    # 5. localization (needed for every goal)
    state = (loc_check or {}).get('state')
    fresh_verified = state == 'VERIFIED' and loc_age_s is not None and loc_age_s <= LOC_FRESH_S
    est_ok = (amcl_confident(amcl, amcl_age_s) and last_verified_age_s is not None
              and last_verified_age_s <= VERIFIED_WITHIN_S)
    loc_ok = fresh_verified or est_ok
    xy = (amcl or {}).get('xy_std_m')
    add('localization', loc_ok, 'Rover knows where it is (localization)',
        f'LiDAR check: {state or "no check"}' + (f' ({int(loc_age_s)} s old)' if loc_age_s else '')
        + (f' • AMCL ±{float(xy):.2f} m' if xy is not None else '')
        + ('' if last_verified_age_s is not None and last_verified_age_s <= VERIFIED_WITHIN_S
           else ' • not VERIFIED in the last 30 min'),
        ['Keep the rover still (B latched).', 'On the Home page press "CHECK MY LOCATION" and wait ~30 s.',
         'If it does not reach VERIFIED, move the rover to a known place (e.g. dhruv room) and check again.'],
        {'label': 'Check my location (Home)', 'href': '/v2/#hmLocSlot'}, 'Automatically when VERIFIED.')

    # 6. camera obstacles reach Nav2
    cam_ok = astra_age_s is not None and astra_age_s <= 2.0
    add('camera', cam_ok, 'Camera obstacle detection (Astra → Nav2)',
        'Camera obstacle data is not reaching Nav2' + ('' if bridge_active else ' (bridge is off)') + '.',
        ['Keep the rover still (B latched) — the CPU is busy for a moment while the bridge starts.',
         'Press "Start camera bridge" and wait ~20 s.'],
        {'label': 'Start camera bridge', 'api': '/api/readiness/bridge'}, 'Automatically when "Live · Nav2" shows.')

    # 7. something to drive to
    add('waypoints', places_count > 0, 'At least one waypoint (optional)',
        'No waypoint saved. Not required: tapping the map and "Move here" also works.',
        ['On the Navigation page tap the map and use "Save waypoint" or "Move here".'],
        {'label': 'Navigation page', 'href': '/v2/mapping'}, 'As soon as a waypoint is saved.')
    items[-1]['optional'] = True

    blocking = [i['id'] for i in items if not i['ok'] and i['id'] in ('mux', 'speed', 'encoders')]
    return {'items': items, 'ready_to_switch_on': not [i for i in items if not i['ok'] and i['id'] in
                                                       ('mux', 'speed', 'encoders', 'estop')],
            'ready_to_drive': not [i for i in items if not i['ok'] and i['id'] not in ('estop', 'waypoints')]
            and bool(auto.get('armed')),
            'blocking': blocking, 'speed_check_running': speed_check_running}
