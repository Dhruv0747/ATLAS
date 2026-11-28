#!/usr/bin/env python3
"""ATLAS master-plan step 6: wheel PID evaluation (read-only, no motion, no ROS). 2026-11-23.

Plan text: "Evaluate wheel PID only if feedback quality permits. PID requires a trustworthy measured variable.
Steering PID requires actual angle feedback." This tool reads the live dashboard status (/api/status on 127.0.0.1,
the light endpoint) and the repo config, and decides:

  four_encoders_trusted   encoder health has no excluded / faulted encoder and the serial link is LIVE
  steering_angle_measured steering feedback is a measured angle (today: "COMMANDED, NOT MEASURED")
  speed_loop_validated    the 3-encoder closed-loop speed control is enabled AND a bounded Speed check passed
  per_wheel_pid_safe_off  config/drive_pid.yaml keeps the per-wheel PID disabled while four encoders are not trusted

Verdict:
  ADVISED      four encoders trusted -> commission the per-wheel PID (developer, atlas_pid_commissioning.py)
  NOT ADVISED  feedback does not permit a per-wheel PID; the evaluation is complete and says what blocks it
  FAIL         an unsafe state (PID enabled without trusted feedback) or no live data
Writes ~/.local/state/project_atlas/pid_eval_<time>.json and records step 6 on the master plan.
"""
import json
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path('/home/jetson/project_atlas')


def evaluate(encoder_health, steer_feedback, speed_loop_enabled, speed_check_passed, drive_pid_text):
    """Pure; unit-tested. encoder_health: dict from /api/status 'encoder_health'."""
    eh = encoder_health or {}
    excluded = list(eh.get('excluded_encoders') or [])
    faults = list(eh.get('faults') or [])
    live = eh.get('link_state') == 'LIVE'
    c = {'live_data': bool(eh) and live}
    c['four_encoders_trusted'] = c['live_data'] and not excluded and not faults and eh.get('state') in ('HEALTHY', 'READY')
    c['steering_angle_measured'] = bool(steer_feedback) and 'NOT MEASURED' not in str(steer_feedback).upper()
    c['speed_loop_validated'] = bool(speed_loop_enabled) and bool(speed_check_passed)
    pid_on = bool(re.search(r'^\s*enabled:\s*true', drive_pid_text or '', re.M))
    c['per_wheel_pid_safe_off'] = (not pid_on) or c['four_encoders_trusted']
    blockers = []
    if excluded:
        blockers.append('encoder M%s excluded' % ','.join(str(e) for e in excluded))
    if faults:
        blockers.append('encoder faults %s' % faults)
    if not c['steering_angle_measured']:
        blockers.append('steering has no angle sensor (commanded only)')
    if not c['live_data'] or not c['per_wheel_pid_safe_off']:
        verdict = 'FAIL'
    elif c['four_encoders_trusted']:
        verdict = 'ADVISED'
    else:
        verdict = 'NOT ADVISED'
    detail = {
        'ADVISED': 'four encoders trusted: per-wheel PID can be commissioned (developer: atlas_pid_commissioning.py)',
        'NOT ADVISED': 'per-wheel PID not advised: %s. Speed control stays the validated 3-encoder speed loop%s.' % (
            '; '.join(blockers) or 'feedback not trusted', '' if c['speed_loop_validated'] else ' (NOT validated)'),
        'FAIL': 'no live encoder data' if not c['live_data'] else 'per-wheel PID is enabled without trusted feedback',
    }[verdict]
    return {'verdict': verdict, 'checks': c, 'blockers': blockers, 'detail': detail,
            'failed': [] if verdict != 'FAIL' else [k for k in ('live_data', 'per_wheel_pid_safe_off') if not c[k]],
            'measured': {'encoder_state': eh.get('state'), 'excluded_encoders': excluded, 'selected_encoders':
                         eh.get('selected_encoders'), 'steering_feedback': steer_feedback, 'per_wheel_pid_enabled': pid_on}}


def main():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8088/api/status', timeout=5) as r:
            ros = json.load(r).get('ros', {})
    except Exception as exc:
        ros = {}
        print(f'no dashboard status: {exc}')
    def val(key):
        v = (ros.get(key) or {}).get('value')
        try:
            return json.loads(v) if isinstance(v, str) else v
        except ValueError:
            return v
    eh = val('encoder_health') or {}
    steer = (val('steering_calibration') or {}).get('feedback')
    try:
        sl = (ROOT / 'config/speed_loop.yaml').read_text()
        loop_on = bool(re.search(r'^\s*enabled:\s*true', sl, re.M))
    except OSError:
        loop_on = False
    import sys
    sys.path.insert(0, str(ROOT / 'scripts'))
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
    import atlas_master_plan
    try:
        pid_text = (ROOT / 'config/drive_pid.yaml').read_text()
    except OSError:
        pid_text = ''
    res = evaluate(eh, steer, loop_on, bool(atlas_master_plan.stage1_evidence()), pid_text)
    res['when'] = time.strftime('%Y-%m-%d %H:%M')
    out = Path.home() / '.local/state/project_atlas' / f'pid_eval_{time.strftime("%Y%m%d_%H%M%S")}.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1))
    try:
        atlas_master_plan.record_later(6, res, out.name)
    except Exception as exc:
        print(f'note: master plan not updated ({exc})')
    print(json.dumps(res, indent=1))
    print(f'STEP 6: {res["verdict"]}')
    print(f'saved {out}')


if __name__ == '__main__':
    main()
