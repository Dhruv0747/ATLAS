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


def read_gate(path=GATE_FILE):
    """{'speed_validated': bool, 'note': str}; anything unreadable is NOT validated."""
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
    return out


class AutonomyArm:
    def __init__(self, runtime_enabled, gate_path=GATE_FILE):
        self.runtime_enabled = bool(runtime_enabled)
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
        gate = read_gate(self.gate_path)
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
