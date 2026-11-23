"""Master-plan progress board (2026-11-23 owner request: "show the master goal progress and help me reach it without
a developer").

Source of the plan: docs/AI_ROBOTICS_ADAPTATION_PHASE0_2026-09-30.md
  Entry gate (must all PASS before Phase-2 features): 1 bounded 20 cm straight run, 2 bounded gentle left/right turn
  sequence, 3 supervised autonomous Dhruv Room -> Hall -> Dhruv Room round trip with safe stop + return home.
  Then the approved execution order (IMU/EKF/TF revalidation ... arm integration).

Status comes only from recorded evidence, never from a button that just says "done":
  stage 1  a Speed check PASS file (bounded straight run, ended by DISTANCE, >= 0.20 m by wheels AND LiDAR ICP)
  stage 2  the Stage-2 gentle turn check (tools/drive/turn_ground_check.py) records every result here; PASS only on
           its own PASS (left arc + right arc + net heading)
  stage 3  the one-click Stage-3 runner records every checker result here; PASS only on "STAGE 3: PASS"
  later steps are engineering work: shown as LOCKED until 1-3 pass, then "needs developer" with what it involves.
Every stage is LOCKED (button disabled) until the stage before it has passed (2026-11-23 owner: "unlock it after the
last one passed").
Read-only except record_stage2()/record_stage3(), which the test tools call after they finish.
"""
import json
import time
from pathlib import Path

STATE_DIR = Path.home() / '.local/state/project_atlas'
PROGRESS_FILE = STATE_DIR / 'master_plan_progress.json'
MIN_STRAIGHT_M = 0.20

# Evidence recorded before this board existed (docs/audits/ATLAS_CURRENT_BLOCKERS.md), so history is not lost.
STAGE3_HISTORY = [
    {'when': '2026-11-22 15:23', 'verdict': 'FAIL', 'score': '3/5', 'note': 'run #7: legs, turn_sign, encoders PASS; '
     'return_home 0.39 m / 59 deg (start pose turned before Go); no B while rolling'},
    {'when': '2026-11-22 16:06', 'verdict': 'FAIL', 'score': '4/5', 'note': 'run #8: legs, safe_stop (0.18 s), '
     'turn_sign, encoders PASS; return_home 0.23 m / 31 deg (180 deg turn at home; fixed: home keeps arrival heading)'},
    {'when': '2026-11-22 19:09', 'verdict': 'FAIL', 'score': '3/5', 'note': 'run #9: start re-oriented by remote '
     'before Go (131 deg); B pressed while not rolling'},
]

GATE = [
    {'id': 'stage1', 'n': 1, 'title': 'Straight run (20 cm, bounded)',
     'goal': 'ATLAS drives a short bounded straight line and stops by itself.',
     'how': ['Open Readiness → Speed check.', 'Clear 1 m in front of ATLAS, E-STOP ready.',
             'Press the Speed check button; ATLAS drives about 0.6 m and stops.'],
     'tool': {'label': 'Open Speed check', 'href': '/v2/readiness'}},
    {'id': 'stage2', 'n': 2, 'title': 'Gentle left/right turns (bounded)',
     'goal': 'ATLAS makes a bounded gentle left turn and right turn with correct wheel/IMU agreement.',
     'how': ['Park ATLAS in the hall (open floor): 1.5 m clear in front, 0.6 m clear on both sides.',
             'Manual mode, E-STOP released, remote in your hand, sticks centred.',
             'Open Stage 2 turns, type the PIN, press START. ATLAS curves gently LEFT ~25 deg, stops, then curves '
             'gently RIGHT ~25 deg and stops (about 30 cm each). B on the remote stops it at any time.'],
     'tool': {'label': 'Open Stage 2 turns', 'href': '/v2/stage2'}},
    {'id': 'stage3', 'n': 3, 'title': 'Dhruv Room → Hall → Dhruv Room (autonomous)',
     'goal': 'One supervised autonomous round trip with a safe stop (B while rolling) and return home.',
     'how': ['Open Stage 3 run and press START.', 'Keep the remote in hand; press B once when PRESS B NOW appears.',
             'Release the E-STOP and turn AUTONOMY ON when asked; help in a doorway if ATLAS gets stuck.'],
     'tool': {'label': 'Open Stage 3 run', 'href': '/v2/stage3'}},
]

LATER = [
    ('IMU / EKF / TF revalidation', 'Stationary bias, controlled turns and full-workload timing; promote no IMU field '
     'without covariance and drift evidence.'),
    ('Nav2 recovery budget audit', 'Prevent endless retry loops and stale commands; mission checkpoint ownership.'),
    ('Wheel PID evaluation', 'Only if encoder feedback is good enough (needs all 4 encoders; M3 is excluded today).'),
    ('Camera VO/VIO (shadow mode)', 'Visual odometry with rate, age, confidence and GOOD/DEGRADED/LOST states.'),
    ('TensorRT YOLO benchmark', 'Optional, resource-capped object detection benchmark.'),
    ('Semantic perception → semantic goals', 'Advisory first; goals only through Nav2 after recorded validation.'),
    ('Robot arm', 'Deferred until the hardware exists and has its own safety plan.'),
]


def _load(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def stage1_evidence(state_dir=STATE_DIR):
    """Newest Speed check PASS that is a real bounded straight run (ended by DISTANCE, >= 0.20 m wheels and ICP)."""
    best = None
    for f in sorted(Path(state_dir).glob('speed_loop_check_*.json')):
        r = _load(f)
        try:
            ok = (r.get('verdict') == 'PASS' and r.get('end_reason') == 'DISTANCE'
                  and float(r.get('wheel_distance_m', 0)) >= MIN_STRAIGHT_M
                  and float(r.get('icp_distance_m', 0)) >= MIN_STRAIGHT_M)
        except (TypeError, ValueError):
            ok = False
        if ok:
            best = {'file': f.name, 'when': time.strftime('%Y-%m-%d %H:%M', time.localtime(f.stat().st_mtime)),
                    'detail': 'bounded straight run: wheels %.2f m, LiDAR %.2f m, ended by distance, coast %.2f m' % (
                        float(r['wheel_distance_m']), float(r['icp_distance_m']), float(r.get('coast_after_stop_m', 0)))}
    return best


def _write(progress_file, data):
    Path(progress_file).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(progress_file) + '.tmp')
    tmp.write_text(json.dumps(data, indent=1), encoding='utf-8')
    tmp.replace(progress_file)


def record_stage2(result, file_name, progress_file=PROGRESS_FILE, clock=time.time):
    """Called by turn_ground_check.py. Keeps the last 30 results; a PASS stays the stage-2 evidence."""
    data = _load(progress_file)
    checks = (result or {}).get('checks') or {}
    run = {'when': time.strftime('%Y-%m-%d %H:%M', time.localtime(clock())), 'verdict': (result or {}).get('verdict'),
           'score': '%d/%d' % (sum(1 for v in checks.values() if v), len(checks)) if checks else '-',
           'file': file_name, 'note': (result or {}).get('detail', ''),
           'failed': list((result or {}).get('failed') or [])[:6]}
    data['stage2_runs'] = (data.get('stage2_runs', []) + [run])[-30:]
    if run['verdict'] == 'PASS':
        data['stage2'] = {'verdict': 'PASS', 'when': run['when'], 'file': file_name,
                          'detail': 'gentle turns: %s (%s)' % (run['note'], run['when'])}
    _write(progress_file, data)


def record_stage4a(result, file_name, progress_file=PROGRESS_FILE, clock=time.time):
    """Called by imu_ekf_tf_parked_check.py (step 4 part A, parked, no motion). A PASS stays the evidence."""
    data = _load(progress_file)
    run = {'when': time.strftime('%Y-%m-%d %H:%M', time.localtime(clock())), 'verdict': (result or {}).get('verdict'),
           'file': file_name, 'note': (result or {}).get('detail', ''),
           'failed': list((result or {}).get('failed') or [])[:8]}
    data['stage4a_runs'] = (data.get('stage4a_runs', []) + [run])[-30:]
    if run['verdict'] == 'PASS':
        data['stage4a'] = dict(run, detail='parked IM10A/EKF/TF check PASS: %s (%s)' % (run['note'], run['when']))
    _write(progress_file, data)


def record_stage3(result, bag, progress_file=PROGRESS_FILE, clock=time.time):
    """Called by the Stage-3 runner after its checker. Keeps the last 30 results."""
    data = _load(progress_file)
    runs = data.get('stage3_runs', [])
    checks = (result or {}).get('checks') or {}
    passed = sum(1 for v in checks.values() if v.get('ok'))
    runs.append({'when': time.strftime('%Y-%m-%d %H:%M', time.localtime(clock())), 'verdict': (result or {}).get('verdict'),
                 'score': '%d/%d' % (passed, len(checks)) if checks else '-', 'bag': bag,
                 'failed': [k for k, v in checks.items() if not v.get('ok')]})
    data['stage3_runs'] = runs[-30:]
    _write(progress_file, data)


def evaluate(state_dir=STATE_DIR, progress_file=PROGRESS_FILE):
    prog = _load(progress_file)
    s1 = stage1_evidence(state_dir)
    s2 = prog.get('stage2')                              # written by record_stage2 on a turn-check PASS
    s2_runs = prog.get('stage2_runs', [])
    runs = STAGE3_HISTORY + prog.get('stage3_runs', [])
    s3_pass = next((r for r in reversed(runs) if r.get('verdict') == 'PASS'), None)
    # 2026-11-23: an explicit, recorded OWNER DECISION may accept combined evidence. It is shown as such, never as a
    # plain checker PASS, and it must name the runs it combines.
    s3_owner = prog.get('stage3_owner_decision') if isinstance(prog.get('stage3_owner_decision'), dict) else None
    best = max(runs, key=lambda r: int(str(r.get('score', '0/1')).split('/')[0] or 0), default=None)
    status = {
        'stage1': ('PASS', s1['detail'] + ' (' + s1['when'] + ')') if s1 else ('NOT DONE', 'No bounded straight-run PASS yet.'),
        'stage2': ('PASS', s2.get('detail', '')) if (s2 or {}).get('verdict') == 'PASS' else
                  ('IN PROGRESS', 'last try %s: %s' % (s2_runs[-1]['when'], s2_runs[-1].get('note') or 'FAIL'))
                  if s2_runs else ('NOT DONE', 'No gentle-turn test recorded yet.'),
        'stage3': ('PASS', 'checker PASS ' + s3_pass['when']) if s3_pass else
                  ('PASS (OWNER DECISION)', 'OWNER DECISION %s: %s' % (s3_owner.get('when', ''), s3_owner.get('text', '')))
                  if s3_owner and s3_owner.get('text') else
                  ('IN PROGRESS' if runs else 'NOT DONE',
                   ('best so far %s (%s)' % (best['score'], best['when'])) if best else 'No run yet.'),
    }
    gate, prev_pass = [], True
    for g in GATE:
        st, detail = status[g['id']]
        passed = st.startswith('PASS')
        # a stage unlocks only after the stage before it has passed; a stage that already passed stays shown
        item = dict(g, status=st if (passed or prev_pass) else 'LOCKED', evidence=detail,
                    locked=not (passed or prev_pass), unlock_after=None if prev_pass else g['n'] - 1)
        if g['id'] == 'stage3':
            item['history'] = runs[-6:]
        elif g['id'] == 'stage2':
            item['history'] = s2_runs[-6:]
        gate.append(item)
        prev_pass = passed
    gate_open = all(g['status'].startswith('PASS') for g in gate)
    # Later steps: every one has a button, LOCKED until the step before it is done (2026-11-23 owner). Step 4 has
    # an owner test for its parked part (A); its turn/full-workload part (B) is developer work, so step 4 never
    # reads PASS from part A alone and steps 5-10 stay locked.
    s4a = prog.get('stage4a') if isinstance(prog.get('stage4a'), dict) else None
    s4_runs = prog.get('stage4a_runs', [])
    later = []
    for i, (t, w) in enumerate(LATER):
        item = {'n': i + 4, 'title': t, 'what': w, 'tool': None, 'status': 'LOCKED',
                'unlock_after': 'entry gate (stages 1-3)' if i == 0 else 'step %d' % (i + 3)}
        if i == 0:
            item['tool'] = {'label': 'Open Stage 4 · parked IMU/EKF/TF check', 'href': '/v2/stage4'}
            item['history'] = s4_runs[-6:]
            if gate_open:
                item['status'] = 'IN PROGRESS' if s4a else 'NOT DONE'
                item['evidence'] = (s4a['detail'] + '. Part B (controlled turns + full-workload timing) needs a '
                                    'developer session.') if s4a else (
                    'last try %s: %s' % (s4_runs[-1]['when'], s4_runs[-1]['verdict']) if s4_runs else
                    'Part A (parked check) not run yet.')
        later.append(item)
    nxt = next((g for g in gate if not g['status'].startswith('PASS')), None)
    if nxt is None:
        next_step = ({'text': 'Entry gate complete! Do step 4 part A: parked IMU/EKF/TF check.', 'href': '/v2/stage4',
                      'label': 'Open Stage 4'} if not s4a else
                     {'text': 'Step 4 part A passed. Part B (controlled turns + full-workload timing) needs a developer '
                              'session.', 'href': None})
    elif nxt.get('tool'):
        next_step = {'text': 'Do stage %d: %s.' % (nxt['n'], nxt['title']),
                     'href': nxt['tool']['href'], 'label': nxt['tool']['label']}
    else:
        next_step = {'text': 'Stage %d (%s) needs a test tool that is not built yet.' % (nxt['n'], nxt['title']),
                     'href': None}
    done = sum(1 for g in gate if g['status'].startswith('PASS'))
    return {'gate': gate, 'later': later, 'gate_done': done, 'gate_total': len(gate), 'gate_open': gate_open,
            'next_step': next_step, 'source': 'docs/AI_ROBOTICS_ADAPTATION_PHASE0_2026-09-30.md',
            'note': 'Status comes only from recorded test results (Speed check, Stage-2 turn check, Stage-3 checker), not from buttons. Each stage unlocks after the one before it passes.'}


def serve(handler, json_response):
    from urllib.parse import urlsplit
    if urlsplit(handler.path).path != '/api/master_plan':
        return False
    json_response(handler, 200, evaluate())
    return True
