#!/usr/bin/env python3
"""ATLAS master-plan step 5: Nav2 recovery budget audit (read-only, no motion, no ROS). 2026-11-23.

Plan text: "Audit Nav2 recovery budgets and mission checkpoint ownership. Prevent endless retry loops; never replay a
stale Twist." This tool reads the files ATLAS is ACTUALLY running (the Nav2 params file is taken from the running
Nav2 processes; the old copy in project_atlas/config is not used live) and checks:

  bt_files_found          both behaviour trees named in the live Nav2 params exist
  bt_retries_bounded      every RecoveryNode has a finite number_of_retries (0..10); no Repeat / RetryUntilSuccessful
                          with -1, no KeepRunningUntilFailure (an endless loop)
  bt_no_spin              no in-place Spin recovery (ATLAS is car-like and cannot spin)
  backup_bounded          every BackUp: distance <= 0.30 m and a time_allowance <= 10 s
  stuck_detection         progress checker: required_movement_radius > 0 and movement_time_allowance 1..60 s
  stale_twist_cut         cmd_vel mux: Nav2 and manual command timeouts <= 0.5 s, watchdog <= 0.1 s (a silent sender is
                          stopped, never replayed)
  mission_home_retries    mission control return-home retries <= 3
  runner_retry_budget     the one-click Stage-3 runner has a Go retry budget (MAX_ATTEMPTS_PER_PLACE <= 30)
It also reports the worst-case time one goal can keep retrying before Nav2 gives up (information).

Writes ~/.local/state/project_atlas/nav2_audit_<time>.json and records step 5 on the master plan.
Usage (on the Jetson):  python3 nav2_recovery_audit.py
"""
import json
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path('/home/jetson/project_atlas')
NAV2_DEFAULT = Path('/home/jetson/project_atlas_ws/src/tortoisebot_bringup/config/nav2_params.yaml')
MAX_BT_RETRIES = 10
MAX_BACKUP_M, MAX_BACKUP_S = 0.30, 10.0
MAX_STUCK_S = 60.0
MAX_CMD_TIMEOUT_S, MAX_WATCHDOG_S = 0.5, 0.1
MAX_HOME_RETRIES = 3
MAX_RUNNER_ATTEMPTS = 30


def _num(pattern, text, default=None):
    m = re.search(pattern, text or '')
    return float(m.group(1)) if m else default


def yaml_value(text, key, section=None):
    """First `key: value` (after `section:` when given). Plain text scan; enough for these flat Nav2 keys."""
    if section and section + ':' in (text or ''):
        text = text.split(section + ':', 1)[1]
    m = re.search(r'^\s*' + re.escape(key) + r':\s*"?([^"#\n]+?)"?\s*(?:#.*)?$', text or '', re.M)
    return m.group(1).strip() if m else None


def audit_bt(xml_text):
    """Return (retries_ok, no_spin, backups_ok, outer_retries, notes) for one behaviour tree. Pure."""
    notes, retries_ok, backups_ok = [], True, True
    root = ET.fromstring(xml_text)
    outer = None
    for el in root.iter():
        tag = el.tag
        if tag == 'RecoveryNode':
            try:
                n = int(el.get('number_of_retries', ''))
            except ValueError:
                n = None
            if n is None or not 0 <= n <= MAX_BT_RETRIES:
                retries_ok = False; notes.append('RecoveryNode %s retries=%s' % (el.get('name'), el.get('number_of_retries')))
            elif outer is None:
                outer = n
        elif tag in ('Repeat', 'RetryUntilSuccessful'):
            k = el.get('num_cycles') or el.get('num_attempts')
            if k is None or int(k) < 0:
                retries_ok = False; notes.append('%s unbounded' % tag)
        elif tag == 'KeepRunningUntilFailure':
            retries_ok = False; notes.append('KeepRunningUntilFailure (endless)')
        elif tag == 'BackUp':
            d = float(el.get('backup_dist', 'inf')); ta = el.get('time_allowance')
            if d > MAX_BACKUP_M or ta is None or float(ta) > MAX_BACKUP_S:
                backups_ok = False; notes.append('BackUp dist=%s time_allowance=%s' % (el.get('backup_dist'), ta))
    no_spin = not any(el.tag == 'Spin' for el in root.iter())
    if not no_spin:
        notes.append('Spin recovery present')
    return retries_ok, no_spin, backups_ok, outer, notes


def evaluate(nav2_text, bt_texts, mux_text, mux_exec, mission_text, mission_exec, runner_text):
    """bt_texts: {path: xml text or None}. *_exec: the service ExecStart line (parameter overrides). Pure."""
    c, m, notes = {}, {}, []
    c['bt_files_found'] = bool(bt_texts) and all(t is not None for t in bt_texts.values())
    r_ok = spin_ok = b_ok = c['bt_files_found']
    outers = []
    for path, txt in bt_texts.items():
        if txt is None:
            notes.append('missing BT ' + path); continue
        try:
            a, b, d, outer, n = audit_bt(txt)
        except ET.ParseError as exc:
            a = b = d = False; outer = None; n = ['BT parse error %s: %s' % (path, exc)]
        r_ok, spin_ok, b_ok = r_ok and a, spin_ok and b, b_ok and d
        notes += n
        outers.append(outer or 0)
    c['bt_retries_bounded'], c['bt_no_spin'], c['backup_bounded'] = r_ok, spin_ok, b_ok
    radius = _num(r'required_movement_radius:\s*([0-9.]+)', nav2_text)
    allow = _num(r'movement_time_allowance:\s*([0-9.]+)', nav2_text)
    c['stuck_detection'] = bool(radius and radius > 0 and allow and 1.0 <= allow <= MAX_STUCK_S)
    m['progress_checker'] = {'required_movement_radius_m': radius, 'movement_time_allowance_s': allow}

    def param(name, code, exec_line):
        v = _num(r'-p\s+' + re.escape(name) + r':=([0-9.]+)', exec_line)
        return v if v is not None else _num(r'declare_parameter\(\s*["\']' + re.escape(name) + r'["\']\s*,\s*([0-9.]+)', code)

    nav_to, man_to, wd = (param('nav_timeout', mux_text, mux_exec), param('manual_timeout', mux_text, mux_exec),
                          param('watchdog_period', mux_text, mux_exec))
    m['mux'] = {'nav_timeout_s': nav_to, 'manual_timeout_s': man_to, 'watchdog_period_s': wd}
    c['stale_twist_cut'] = (nav_to is not None and man_to is not None and wd is not None
                            and nav_to <= MAX_CMD_TIMEOUT_S and man_to <= MAX_CMD_TIMEOUT_S and wd <= MAX_WATCHDOG_S)
    home = param('home_max_retries', mission_text, mission_exec)
    m['mission_home_max_retries'] = home
    c['mission_home_retries'] = home is not None and 0 <= home <= MAX_HOME_RETRIES
    mm = re.search(r'^MAX_ATTEMPTS_PER_PLACE\s*=\s*([0-9]+)', runner_text or '', re.M)
    budget = float(mm.group(1)) if mm else None
    m['runner_max_attempts_per_place'] = budget
    c['runner_retry_budget'] = budget is not None and 1 <= budget <= MAX_RUNNER_ATTEMPTS
    # information: worst case one goal keeps trying = (outer retries + 1) x (stuck allowance x 2 + backup 5 s + wait 2 s)
    if outers and allow:
        m['worst_case_goal_retry_s'] = round((max(outers) + 1) * (2 * allow + 7.0))
    m['bt_outer_retries'] = outers
    failed = [k for k, v in c.items() if not v]
    detail = 'BT retries %s, stuck after %ss, mux cut %s/%s s, home retries %s, runner budget %s, worst case %s s' % (
        outers, allow, nav_to, man_to, home, budget, m.get('worst_case_goal_retry_s'))
    return {'verdict': 'PASS' if not failed else 'FAIL', 'checks': c, 'measured': m, 'failed': failed,
            'notes': notes, 'detail': detail}


def _read(path):
    try:
        return Path(path).read_text(encoding='utf-8')
    except OSError:
        return None


def _exec_line(unit):
    try:
        out = subprocess.run(['systemctl', '--user', 'cat', unit], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return ''
    lines = [l for l in out.splitlines() if l.startswith('ExecStart=') and l.strip() != 'ExecStart=']
    return lines[-1] if lines else ''


def live_nav2_params():
    """The --params-file the running Nav2 servers were started with (falls back to the workspace default)."""
    try:
        ps = subprocess.run(['ps', '-eo', 'args'], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        ps = ''
    for line in ps.splitlines():
        if 'bt_navigator' in line:
            for p in re.findall(r'--params-file\s+(\S+)', line):
                if p.endswith('.yaml') and 'nav2' in p:
                    return Path(p)
    return NAV2_DEFAULT


def main():
    nav2 = live_nav2_params()
    nav2_text = _read(nav2) or ''
    bts = [yaml_value(nav2_text, 'default_nav_to_pose_bt_xml'), yaml_value(nav2_text, 'default_nav_through_poses_bt_xml')]
    bt_texts = {p: _read(p) for p in bts if p}
    res = evaluate(nav2_text, bt_texts, _read(ROOT / 'scripts/atlas_cmd_vel_mux.py') or '',
                   _exec_line('atlas-cmd-vel-mux.service'), _read(ROOT / 'scripts/atlas_mission_control.py') or '',
                   _exec_line('atlas-mission-control.service'), _read(ROOT / 'scripts/atlas_stage3_runner.py') or '')
    res['nav2_params_file'] = str(nav2)
    res['bt_files'] = list(bt_texts)
    res['when'] = time.strftime('%Y-%m-%d %H:%M')
    out = Path.home() / '.local/state/project_atlas' / f'nav2_audit_{time.strftime("%Y%m%d_%H%M%S")}.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1))
    try:
        import sys
        sys.path.insert(0, str(ROOT / 'scripts'))
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
        import atlas_master_plan
        atlas_master_plan.record_later(5, res, out.name)
    except Exception as exc:
        print(f'note: master plan not updated ({exc})')
    print(json.dumps(res, indent=1))
    print(f'STEP 5: {res["verdict"]}')
    print(f'saved {out}')


if __name__ == '__main__':
    main()
