"""Runtime autonomy ON/OFF for the cmd_vel mux (2026-11-15, owner request: dashboard autonomy button).

Pure state, no ROS. The boot default is OFF. ``ATLAS_MANUAL_ONLY=1`` stays the hard lock unless the unit also sets
``ATLAS_AUTONOMY_RUNTIME_ARM=1``; then manual-only is lifted only while this arm is ON.

Arming (ON) is refused unless ALL hold:
  * runtime arming is enabled for this mux unit;
  * the stop latch (E-STOP) is LATCHED  -> the operator arms while stopped, then releases deliberately;
  * the rover is not being commanded to move;
  * encoder health is fresh (<= 2 s) and reports autonomy_ready;
  * the gate file (config/autonomy_gate.yaml) says speed_validated: true — set only after the autonomous speed
    calibration (2026-11-15: a 0.07 m/s command drove ~0.4 m/s open-loop).
Disarming (OFF) is always accepted. Any new E-STOP latch (released -> latched edge) disarms automatically.
"""
from pathlib import Path

GATE_FILE = Path(__file__).resolve().parents[1] / 'config' / 'autonomy_gate.yaml'
ENCODER_MAX_AGE_S = 2.0


STATE_DIR = Path.home() / '.local/state/project_atlas'
SPEED_LOOP_CFG = Path(__file__).resolve().parents[1] / 'config' / 'speed_loop.yaml'
SPEED_LOOP_CODE = (Path(__file__).resolve().parent / 'atlas_speed_loop.py',
                   Path(__file__).resolve().parent / 'yahboom_base.py')
SPEED_TARGETS = (0.15,)      # requested speed = Nav2 desired_linear_vel (mux scales it to 0.075 while DEGRADED)
REQUIRED_PASSES = 2          # 2026-11-15: two independent PASS runs (0.05 m/s after scaling is below the crawl floor)
EVIDENCE_MAX_AGE_S = 30 * 86400


def speed_evidence(state_dir=STATE_DIR, cfg=SPEED_LOOP_CFG, code=SPEED_LOOP_CODE, now=None):
    """2026-11-15 self-service unlock: the owner-run speed ground check (speed_loop_ground_check.py) writes
    speed_loop_check_*.json. Speed counts as validated when the speed loop is enabled and there is a PASS at every
    SPEED_TARGETS speed that is newer than the speed-loop config and code (any change needs a fresh check) and at
    most 30 days old. Returns {'ok', 'enabled', 'passed': [targets], 'missing': [targets], 'latest': {target: summary}}."""
    import json
    import time as _time
    now = _time.time() if now is None else now
    out = {'ok': False, 'enabled': False, 'passed': [], 'missing': list(SPEED_TARGETS), 'latest': {}}
    try:
        text = Path(cfg).read_text(encoding='utf-8')
        out['enabled'] = any(l.split('#', 1)[0].strip().replace(' ', '') == 'enabled:true' for l in text.splitlines())
        newest_change = max([Path(cfg).stat().st_mtime] + [Path(c).stat().st_mtime for c in code if Path(c).exists()])
    except OSError:
        return out
    for f in sorted(Path(state_dir).glob('speed_loop_check_*.json')):
        try:
            r = json.loads(f.read_text(encoding='utf-8'))
            mtime = f.stat().st_mtime
            target = float(r.get('requested_mps', r.get('target_mps')))
        except (OSError, ValueError, TypeError):
            continue
        for t in SPEED_TARGETS:
            if abs(target - t) < 0.005:
                fresh = mtime > newest_change and now - mtime <= EVIDENCE_MAX_AGE_S
                out['latest'][t] = {'verdict': r.get('verdict'), 'fresh': fresh, 'file': f.name, 'time': mtime,
                                    'steady_mean_mps': r.get('steady_mean_mps'), 'peak_mps': r.get('peak_mps'),
                                    'end_reason': r.get('end_reason'),
                                    'failed_checks': [k for k, v in (r.get('checks') or {}).items() if not v]}
                if fresh and r.get('verdict') == 'PASS':
                    out['passed'].append(t)
    out['missing'] = [t for t in SPEED_TARGETS if out['passed'].count(t) < REQUIRED_PASSES]
    out['passes_needed'] = REQUIRED_PASSES
    out['ok'] = out['enabled'] and not out['missing']
    return out


def read_gate(path=GATE_FILE, evidence=None):
    """{'speed_validated': bool, 'note': str}; anything unreadable is NOT validated.
    Validated by the manual flag OR by fresh PASS evidence from the owner-run speed check (speed_evidence)."""
    out = {'speed_validated': False, 'note': ''}
    try:
        for line in Path(path).read_text(encoding='utf-8').splitlines():
            line = line.split('#', 1)[0].strip()
            if ':' not in line:
                continue
            key, value = (part.strip() for part in line.split(':', 1))
            if key == 'speed_validated':
                out['speed_validated'] = value.lower() == 'true'
            elif key == 'note':
                out['note'] = value.strip('\'"')
    except OSError:
        out['note'] = 'gate file missing'
    if not out['speed_validated']:
        ev = speed_evidence() if evidence is None else evidence
        if ev.get('ok'):
            out['speed_validated'], out['note'] = True, 'speed check PASS evidence'
        elif not ev.get('enabled'):
            out['note'] = 'speed loop not enabled'
        else:
            have = len([t for t in ev.get('passed', []) if t in ev.get('missing', [])])
            out['note'] = ('run the Speed check at ' + ' and '.join(f'{t:.2f}' for t in ev.get('missing', []))
                           + f' m/s ({have}/{REQUIRED_PASSES} PASS)')
    return out


class AutonomyArm:
    def __init__(self, runtime_enabled, gate_path=GATE_FILE, evidence_override=None):
        self.runtime_enabled = bool(runtime_enabled)
        self.evidence_override = evidence_override          # tests only
        self.gate_path = gate_path
        self.armed = False
        self.last_change = 'boot: OFF'
        self._was_latched = None

    def blockers(self, stop_latched, moving, encoder_health, encoder_age_s):
        why = []
        if not self.runtime_enabled:
            why.append('runtime autonomy switch not enabled on this mux')
        if not stop_latched:
            why.append('latch the E-STOP first (arm while stopped)')
        if moving:
            why.append('rover is being commanded to move')
        if encoder_age_s is None or not 0 <= encoder_age_s <= ENCODER_MAX_AGE_S:
            why.append('encoder health stale')
        elif not (encoder_health or {}).get('autonomy_ready'):
            why.append('encoder health not autonomy-ready')
        gate = read_gate(self.gate_path, evidence=self.evidence_override)
        if not gate['speed_validated']:
            why.append('autonomous speed not validated' + (f" ({gate['note']})" if gate['note'] else ''))
        return why

    def arm(self, stop_latched, moving, encoder_health, encoder_age_s):
        why = self.blockers(stop_latched, moving, encoder_health, encoder_age_s)
        if why:
            return False, 'AUTONOMY ON refused: ' + '; '.join(why)
        self.armed = True
        self.last_change = 'ON by operator'
        return True, 'AUTONOMY ON. Release the E-STOP to let Nav2 drive; any E-STOP turns it OFF.'

    def disarm(self, reason='OFF by operator'):
        was = self.armed
        self.armed = False
        self.last_change = reason
        return was

    def observe_latch(self, latched):
        """Call on every stop-state observation. A released -> latched edge disarms."""
        edge = self._was_latched is False and bool(latched)
        self._was_latched = bool(latched)
        if edge and self.armed:
            self.disarm('OFF: E-STOP latched')
            return True
        return False

    def manual_only(self, env_manual_only):
        if not env_manual_only:
            return False
        return not (self.runtime_enabled and self.armed)

    def status(self, stop_latched, moving, encoder_health, encoder_age_s):
        return {'runtime_enabled': self.runtime_enabled, 'armed': self.armed, 'last_change': self.last_change,
                'arm_blockers': [] if self.armed else self.blockers(stop_latched, moving, encoder_health,
                                                                     encoder_age_s)}
