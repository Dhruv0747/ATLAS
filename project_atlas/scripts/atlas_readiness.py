"""Autonomy readiness checklist (2026-11-15, owner: "tell me why autonomy won't move, how to clear it, open the test
page, and unlock by itself when the test passes — no developer needed"). Pure; the web layer collects the inputs.

Every item: id, ok, title, why (current reason), steps (Hindi, what to physically do), action (button: page link or
API call) and unlocks_by (what clears it). Items that the owner cannot fix from the dashboard say so plainly.
Owner decision 2026-11-15 ("Owner sign-off test"): there is NO override for safety items (mux, speed, encoders,
E-STOP, localization, camera); each is cleared only by its owner-run test/check. Only 'waypoints' is optional.
"""

LOC_FRESH_S = 120.0


def _fmt(t):
    return f'{t:.2f} m/s'


def checklist(policy, encoder_health, encoder_age_s, loc_check, loc_age_s, astra_age_s, bridge_active,
              speed_ev, gate, places_count, speed_check_running=False):
    items = []
    auto = (policy or {}).get('autonomy') or {}
    latched = (policy or {}).get('stop_latched')

    def add(id_, ok, title, why, steps, action=None, unlocks_by=''):
        items.append({'id': id_, 'ok': bool(ok), 'title': title, 'why': why if not ok else '',
                      'steps': steps if not ok else [], 'action': action if not ok else None,
                      'unlocks_by': unlocks_by})

    # 1. mux link
    add('mux', policy is not None, 'Safety controller (mux) online',
        'Dashboard को mux से ताज़ा जानकारी नहीं मिल रही।',
        ['Rover चालू है और Wi-Fi से जुड़ा है, यह देखें।', '30 second रुककर page refresh करें।',
         'फिर भी न आए तो rover restart करें।'], None, 'mux से ताज़ा status आते ही अपने आप।')

    # 2. speed (closed loop + owner-run ground check)
    enabled = bool((speed_ev or {}).get('enabled'))
    missing = (speed_ev or {}).get('missing', [])
    latest = (speed_ev or {}).get('latest', {})
    fails = []
    for t, r in sorted(latest.items()):
        if r.get('verdict') != 'PASS' and r.get('fresh'):
            fails.append(f"{_fmt(float(t))}: FAIL ({', '.join(r.get('failed_checks') or [r.get('end_reason') or '?'])})")
    if not enabled:
        why = 'Speed control (closed loop) अभी बंद है, इसलिए rover बताई गई speed से नहीं चलता।'
        steps = ['यह setting developer/deploy से चालू होती है (config/speed_loop.yaml).',
                 'चालू होने के बाद नीचे का Speed check करें।']
    else:
        why = 'Speed check बाकी है: ' + ', '.join(_fmt(t) for t in missing) + (' • पिछला: ' + '; '.join(fails) if fails else '')
        steps = ['Rover को खुली जगह रखें: आगे कम से कम 1.5 m खाली, आगे 0.6 m के अंदर कुछ न हो।',
                 'Remote हाथ में रखें, sticks बीच में; E-STOP (B) छोड़ दें।',
                 'Readiness page पर PIN डालकर "Speed check 0.10" दबाएँ। Rover ~0.6 m धीरे आगे चलेगा और रुकेगा।',
                 'फिर rover वापस लाकर "Speed check 0.15" करें।',
                 'दोनों PASS होते ही यह रुकावट अपने आप हट जाएगी। कुछ गड़बड़ लगे तो B दबाएँ।']
    add('speed', bool(gate.get('speed_validated')), 'Speed sahi (commanded = actual)', why, steps,
        {'label': 'Speed check page खोलें', 'href': '/v2/readiness#speed'} if enabled else None,
        'दोनों speeds पर PASS होते ही अपने आप (config या code बदलने पर फिर से check चाहिए)।')

    # 3. encoders
    enc_ok = encoder_age_s is not None and 0 <= encoder_age_s <= 2 and bool((encoder_health or {}).get('autonomy_ready'))
    if encoder_age_s is None or not 0 <= encoder_age_s <= 2:
        ewhy = 'Encoder (पहियों के sensor) की जानकारी नहीं आ रही।'
    elif not (encoder_health or {}).get('navigation_validated'):
        ewhy = 'Encoder अभी autonomy के लिए validated नहीं हैं (ground round-trip check बाकी)।'
    else:
        ewhy = f"Encoder हालत: {(encoder_health or {}).get('state', '?')} — {(encoder_health or {}).get('reason', '')}"
    add('encoders', enc_ok, 'Wheel encoders ready', ewhy,
        ['Motor & Encoder Test Lab खोलें और चारों पहियों की गिनती देखें (rover उठाकर या खड़ा रखकर)।',
         'कोई पहिया 0 या उल्टा गिने तो उसकी wire/connector check करें।',
         'Wiring ठीक है पर फिर भी blocked हो तो developer से बात करें।'],
        {'label': 'Motor & Encoder Test Lab', 'href': '/v2/testlab'}, 'Encoder health ठीक होते ही अपने आप।')

    # 4. E-STOP latched to switch ON
    add('estop', bool(latched) or auto.get('armed'), 'E-STOP latched (to switch ON)',
        'Autonomous चालू करने के लिए पहले rover रुका हुआ (E-STOP latched) होना चाहिए।',
        ['Remote पर B दबाएँ।', 'फिर PIN डालकर "Autonomous mode" दबाएँ।', 'उसके बाद remote से E-STOP छोड़ें (sticks बीच, LB दबाकर छोड़ें)।'],
        None, 'B दबाते ही।')

    # 5. localization (needed for every goal)
    state = (loc_check or {}).get('state')
    loc_ok = state == 'VERIFIED' and loc_age_s is not None and loc_age_s <= LOC_FRESH_S
    add('localization', loc_ok, 'Rover को अपनी जगह पता है (localization)',
        f'Localization: {state or "कोई check नहीं"}' + (f' ({int(loc_age_s)} s पुराना)' if loc_age_s else ''),
        ['Rover को खड़ा रखें (B latched)।', 'Home page पर "CHECK MY LOCATION" दबाएँ और ~30 s रुकें।',
         'VERIFIED न आए तो rover को किसी पहचानी जगह (जैसे dhruv room) ले जाकर फिर check करें।'],
        {'label': 'Check my location (Home)', 'href': '/v2/#hmLocSlot'}, 'VERIFIED आते ही अपने आप।')

    # 6. camera obstacles reach Nav2
    cam_ok = astra_age_s is not None and astra_age_s <= 2.0
    add('camera', cam_ok, 'Camera obstacle detection (Astra → Nav2)',
        'Camera की obstacle जानकारी Nav2 तक नहीं पहुँच रही' + ('' if bridge_active else ' (bridge बंद है)') + '।',
        ['Rover खड़ा रखें (B latched) — bridge चालू होते समय CPU थोड़ी देर busy रहता है।',
         '"Camera bridge चालू करें" दबाएँ, ~20 s रुकें।'],
        {'label': 'Camera bridge चालू करें', 'api': '/api/readiness/bridge'}, '"Live · Nav2" आते ही अपने आप।')

    # 7. something to drive to
    add('waypoints', places_count > 0, 'कम से कम एक waypoint (optional)',
        'कोई waypoint नहीं है। यह ज़रूरी नहीं: map tap करके "Move here" भी चलता है।',
        ['Navigation page पर map tap करें और "Save waypoint" या "Move here" इस्तेमाल करें।'],
        {'label': 'Navigation page', 'href': '/v2/mapping'}, 'Waypoint save होते ही।')
    items[-1]['optional'] = True

    blocking = [i['id'] for i in items if not i['ok'] and i['id'] in ('mux', 'speed', 'encoders')]
    return {'items': items, 'ready_to_switch_on': not [i for i in items if not i['ok'] and i['id'] in
                                                       ('mux', 'speed', 'encoders', 'estop')],
            'ready_to_drive': not [i for i in items if not i['ok'] and i['id'] not in ('estop', 'waypoints')]
            and bool(auto.get('armed')),
            'blocking': blocking, 'speed_check_running': speed_check_running}
