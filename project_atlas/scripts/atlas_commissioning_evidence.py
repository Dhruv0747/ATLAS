"""Read-only readiness projection and bounded evidence in the existing SQLite DB.

This module never publishes commands, opens hardware, applies calibration or
unlocks autonomy. A PASS is evidence of a specific property, not drive authority.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import uuid


STATES = frozenset(('NOT_TESTED', 'IN_PROGRESS', 'PASS', 'FAIL', 'WARNING',
                    'OBSERVED', 'STALE', 'RETEST_REQUIRED', 'EXCLUDED'))
# Files deliberately exclude dashboard/UI: changing a label cannot invalidate
# physical encoder evidence. Relevant owner implementation changes DO invalidate.
BASE = ('scripts/yahboom_base.py', 'scripts/Rosmaster_Lib.py')
STEERING = BASE + ('scripts/atlas_steering_commission.py', 'config/steering_calibration.json')
ENCODER = BASE + ('scripts/atlas_encoder_selection.py', 'config/encoder_selection.yaml')
IMU = ('scripts/atlas_im10a_observer.py', 'config/im10a_mounting.yaml',
       'config/im10a_gyro_bias.json')
ULTRASONIC = ('scripts/ultrasonic_arduino_bridge.py', 'scripts/atlas_ultrasonic_validity.py')
SAFETY = ('scripts/atlas_cmd_vel_mux.py', 'scripts/atlas_ultrasonic_validity.py', 'config/nav2_params.yaml')
# Ordered gates, one next action. No hard dependency on M4 or on an unfused IMU.
GATES = {
    'steering_front': ('steering', 'Front safe centre / left / right', STEERING,
                       'Use existing lifted-wheel steering controls; verify, explicitly save, then record the front physical limits.'),
    'steering_rear': ('steering', 'Rear safe centre / left / right', STEERING,
                      'Verify and save rear physical centre and safe endpoints using the existing owner.'),
    'encoder_direction': ('encoders', 'M1–M3 direction observation', ENCODER,
                          'Review retained direction evidence before deciding whether any new direction test is justified.'),
    'encoder_metric': ('encoders', 'Independent measured encoder distance', ENCODER,
                       'Measure a straight distance accurately: Run A proposes scale; a separate Run B validates it. Do not reuse the approximate 40 cm run.'),
    'stopping': ('encoders', 'Physical stopping response', ENCODER + SAFETY,
                 'After metric validation, measure stopping response and physical stopping distance separately.'),
    'ultrasonic_safety': ('distance', 'Secondary near-field safety qualification',
                          ULTRASONIC + SAFETY,
                          'Qualify valid echoes, noise, stale/disconnected data and actual directional stop inhibition; LiDAR stays primary.'),
    'localization': ('system', 'Localization / TF reliability',
                     ENCODER + ('config/atlas_ekf.yaml', 'config/nav2_params.yaml'),
                     'Verify localization and TF timing under the normal workload before a room mission.'),
    'remote_stop': ('system', 'Physical remote stop / release',
                    BASE + ('scripts/atlas_cmd_vel_mux.py', 'scripts/atlas_remote_stop.py'),
                    'Verify stop and deliberate reset through the existing remote; online telemetry alone cannot prove stopping.'),
    'imu_dynamic': ('imu', 'Independent clockwise / counter-clockwise IMU turn', IMU + ('config/atlas_ekf.yaml',),
                    'Record synchronized gyro against independently measured turns; no Euler-derived gain or automatic EKF enable.'),
    'camera_bounds': ('camera', 'Physical camera bounds',
                       ('scripts/ultrasonic_arduino_bridge.py', 'systemd/user/atlas-uno-r4-sensor-hub.service.d/camera-home.conf'),
                       'Verify safe pan/tilt endpoints with the existing owner; PWM limits are not mechanical limits.'),
    'm4_feedback': ('encoders', 'M4 feedback exclusion', ('config/encoder_selection.yaml',),
                    'Keep excluded feedback out of odometry; the drive motor is separate.'),
    'telemetry_hardware': ('system', 'Non-motion hardware observation', (), 'Inspect live sensor reports.'),
    'telemetry_imu': ('imu', 'Stationary IMU observation', IMU, 'Observe bias/noise without qualifying dynamic fusion.'),
    'telemetry_gnss': ('gnss', 'GNSS observation', (), 'Fresh NMEA is not position accuracy.'),
    **{'distance_' + side: ('distance', side + ' known-distance observation',
        ULTRASONIC, 'Compare a known target and record error, not a safety PASS.')
       for side in ('front', 'rear', 'left', 'right')},
}
MANDATORY = ('steering_front', 'steering_rear', 'encoder_direction', 'encoder_metric',
             'stopping', 'ultrasonic_safety', 'localization', 'remote_stop')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False,
                                     separators=(',', ':')).encode()).hexdigest()


def utc():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


class EvidenceLedger:
    def __init__(self, root, database):
        self.root, self.database = Path(root), Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS results (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS evidence (id INTEGER PRIMARY KEY, test_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL)')
            # The latest state for each known gate is pinned separately from the
            # 500-entry event journal, so routine checks cannot evict a valid PASS.
            db.execute('CREATE TABLE IF NOT EXISTS evidence_current (gate TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS evidence_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            self._migrate(db)
            db.commit()

    def connect(self):
        return closing(sqlite3.connect(self.database, timeout=2))

    def signature(self, gate):
        if gate not in GATES:
            raise ValueError('Unknown evidence gate')
        sources = {}
        for name in GATES[gate][2]:
            path = self.root / name
            if path.exists() and name == 'config/steering_calibration.json' and gate in ('steering_front','steering_rear'):
                # Rear-only changes and re-saving identical values do not erase
                # a front verification (or vice versa). Timestamp is not geometry.
                saved = json.loads(path.read_text(encoding='utf-8'))
                sources[name] = digest(saved.get('steering', {}).get(gate.split('_')[1]))
            else:
                sources[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        return {'hash': digest(sources), 'sources': sources}

    def _append(self, db, record):
        payload = json.dumps(record, allow_nan=False)
        if len(payload.encode()) > 65536:
            raise ValueError('Evidence exceeds 64 KiB')
        db.execute('INSERT INTO evidence(test_id,payload) VALUES (?,?)', (record['test_id'], payload))
        db.execute('INSERT OR REPLACE INTO evidence_current(gate,payload) VALUES (?,?)', (record['gate'], payload))
        db.execute('DELETE FROM evidence WHERE id NOT IN (SELECT id FROM evidence ORDER BY id DESC LIMIT 500)')

    def _record(self, gate, status, measurements, source, confirmation, signature):
        if gate not in GATES or status not in STATES:
            raise ValueError('Unknown gate or state')
        if status == 'PASS' and (not confirmation or not measurements or not signature.get('sources')):
            raise ValueError('PASS requires scoped configuration, measurements and confirmation')
        return {'schema_version': 2, 'test_id': uuid.uuid4().hex, 'gate': gate,
                'subsystem': GATES[gate][0], 'status': status, 'timestamp': utc(),
                'configuration_hash': signature.get('hash'),
                'configuration_sources': signature.get('sources', {}),
                'hardware_revision': 'NOT independently identified; report hardware changes explicitly',
                'measurements': measurements, 'operator_confirmation': confirmation,
                'evidence_source': source, 'invalidated_by': None, 'retest_reason': None}

    def record(self, gate, status, measurements, source, confirmation=None, signature=None):
        # Internal test evaluators only. No HTTP endpoint accepts arbitrary PASS.
        record = self._record(gate, status, measurements, source, confirmation,
                              signature if signature is not None else self.signature(gate))
        with self.connect() as db:
            self._append(db, record)
            db.commit()
        return record

    def _migrate(self, db):
        if db.execute("SELECT 1 FROM evidence_meta WHERE key='legacy-v1'").fetchone():
            return
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='results'").fetchone():
            for (payload,) in db.execute('SELECT payload FROM results ORDER BY id ASC').fetchall()[-500:]:
                old = json.loads(payload)
                gate = observation_gate(old.get('kind'), old.get('side'))
                if gate:
                    # An old hardware 'PASS' never becomes a physical PASS.
                    r = self._record(gate, 'FAIL' if old.get('state') == 'FAIL' else 'OBSERVED',
                                     old, 'legacy results table; telemetry only', None, {})
                    r['timestamp'] = old.get('timestamp_utc', r['timestamp'])
                    self._append(db, r)
        db.execute("INSERT INTO evidence_meta VALUES ('legacy-v1', 'complete')")

    def import_direction_observation(self):
        """One-time historical OBSERVED, never relabelled as current physical PASS."""
        path = self.root.parent / 'docs/THREE_ENCODER_GROUND_OBSERVATION_2026-09-17.md'
        if not path.exists():
            path = self.root / 'docs/THREE_ENCODER_GROUND_OBSERVATION_2026-09-17.md'
        if not path.exists():
            return
        with self.connect() as db:
            if db.execute("SELECT 1 FROM evidence_meta WHERE key='direction-20260917'").fetchone():
                return
            if not db.execute("SELECT 1 FROM evidence_current WHERE gate='encoder_direction'").fetchone():
                r = self._record('encoder_direction', 'OBSERVED',
                    {'selected': [1, 2, 3], 'physical_distance_precision': 'UNCONFIRMED',
                     'scope': 'Documented direction/count observation only; metric and stopping validation remain open'},
                    {'document': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()},
                    'Historical operator report; not a new test', {})
                # Unknown historical configuration is intentionally not bound to
                # today's settings; readiness calls it reviewable, not a PASS.
                r['timestamp'] = '2026-09-17 (historical report)'
                self._append(db, r)
            db.execute("INSERT INTO evidence_meta VALUES ('direction-20260917', 'imported')")
            db.commit()

    def import_configured_exclusion(self):
        """Record configuration, not proof of a working or broken motor."""
        path = self.root / 'config/encoder_selection.yaml'
        if not path.exists():
            return
        try:
            import yaml
        except ImportError:
            # The live ROS stack already requires PyYAML. No guessed YAML
            # parser or dependency install on offline development machines.
            return
        config = yaml.safe_load(path.read_text(encoding='utf-8'))
        if not isinstance(config, dict) or config.get('excluded_encoders') != [4]:
            return
        with self.connect() as db:
            if db.execute("SELECT 1 FROM evidence_current WHERE gate='m4_feedback'").fetchone():
                return
            r = self._record('m4_feedback', 'EXCLUDED',
                             {'excluded_feedback': [4], 'drive_motor': 'not disabled by encoder selection'},
                             'config/encoder_selection.yaml; configuration only, not a motor test',
                             None, self.signature('m4_feedback'))
            self._append(db, r)
            db.commit()

    def current(self, active_observation_id=None):
        with self.connect() as db:
            rows = {gate: json.loads(payload) for gate, payload in db.execute('SELECT gate,payload FROM evidence_current')}
        out = []
        for gate, (subsystem, title, _, action) in GATES.items():
            r = rows.get(gate, {'gate': gate, 'subsystem': subsystem, 'status': 'NOT_TESTED',
                                 'test_id': None, 'invalidated_by': None, 'retest_reason': None})
            r = dict(r, title=title, next_action=action)
            old_hash = r.get('configuration_hash')
            now = self.signature(gate)
            if old_hash and old_hash != now['hash'] and r['status'] != 'RETEST_REQUIRED':
                changed = [k for k in set(now['sources']) | set(r.get('configuration_sources', {}))
                           if now['sources'].get(k) != r.get('configuration_sources', {}).get(k)]
                r.update(recorded_status=r['status'], status='RETEST_REQUIRED',
                         invalidated_by=changed, retest_reason='Relevant source/calibration changed; the previous result does not prove the current configuration.')
            elif r['status'] == 'IN_PROGRESS' and (not active_observation_id or r.get('measurements', {}).get('observation_id') != active_observation_id):
                r.update(recorded_status='IN_PROGRESS', status='RETEST_REQUIRED',
                         invalidated_by='interrupted test', retest_reason='No terminal result was recorded; do not infer success.')
            r['current_configuration_hash'] = now['hash']
            out.append(r)
        return out

    def history(self):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT payload FROM evidence ORDER BY id DESC LIMIT 100')]

    def invalidate(self, gate, reason, expected_test_id):
        if gate not in GATES or not isinstance(reason, str) or not 8 <= len(reason.strip()) <= 500:
            raise ValueError('Choose a gate and explain the hardware/configuration change (8–500 characters)')
        with self.connect() as db:
            row = db.execute('SELECT payload FROM evidence_current WHERE gate=?', (gate,)).fetchone()
            old = json.loads(row[0]) if row else {}
            if old.get('test_id') != expected_test_id:
                raise ValueError('Evidence changed; reload before invalidating')
            r = self._record(gate, 'RETEST_REQUIRED', {}, 'operator reported change', reason.strip(), self.signature(gate))
            r.update(invalidated_by=old.get('test_id'), retest_reason=reason.strip())
            self._append(db, r)
            db.commit()
        return r


def observation_gate(kind, side=None):
    return ('distance_' + side if side in ('front', 'rear', 'left', 'right') else None) if kind == 'distance' else {
        'hardware': 'telemetry_hardware', 'imu': 'telemetry_imu', 'gnss': 'telemetry_gnss'}.get(kind)


def readiness(records, data):
    """Advisory only; does not change the mux, navigation_validated or EKF."""
    from atlas_commissioning import decoded, fresh
    by_gate = {r['gate']: r for r in records}
    required = list(MANDATORY)
    # A runtime diagnostic label is not proof of the running EKF configuration.
    # Dynamic IMU remains visible as pending, not mandatory for wheel-only work.
    completed = [g for g in required if by_gate[g]['status'] == 'PASS']
    # Retain the documented direction observation without re-running that old
    # test just to collect another informal answer. It is NOT a physical PASS.
    retained = by_gate['encoder_direction']['status'] == 'OBSERVED'
    unresolved = [g for g in required if g not in completed and not (g == 'encoder_direction' and retained)]
    policy, enc = decoded(data, 'control_policy'), decoded(data, 'encoder_health')
    blocked = []
    if not fresh(data, 'control_policy', 1):
        blocked.append('Control-policy telemetry stale or missing')
    if not fresh(data, 'encoder_health', 1) or enc.get('packet_fresh') is not True:
        blocked.append('Encoder transport not fresh; restore communications before a physical test')
    if enc.get('faults'):
        blocked.append('Selected encoder fault: ' + str(enc['faults']))
    steer = decoded(data, 'steering_calibration')
    if fresh(data, 'steering_calibration', 1) and steer.get('locked'):
        blocked.append('Steering commissioning still inhibits traction; no automatic release')
    if policy.get('manual_only') is True:
        blocked.append('Runtime manual-only gate remains active')
    if enc.get('navigation_validated') is not True:
        blocked.append('Encoder navigation validation has not been granted')
    next_gate = unresolved[0] if unresolved else None
    return {'state': 'AUTONOMY BLOCKED', 'completed': completed,
            'retained_observations': ['encoder_direction'] if retained else [],
            'current_step': next_gate, 'next_required_step': next_gate,
            'primary_blocker': by_gate[next_gate]['title'] if next_gate else 'Separate safety / deployment review required',
            'next_action': by_gate[next_gate]['next_action'] if next_gate else 'Review all recorded results and current runtime before authorizing any autonomous mission.',
            'blocked': blocked, 'retest_required': [r['gate'] for r in records if r['status'] == 'RETEST_REQUIRED'],
            'optional_pending': ['imu_dynamic', 'camera_bounds'],
            'authority': 'READ-ONLY commissioning guidance; never releases motion or enables fusion',
            'physical_tests_automatically_started': False,
            'fallback': {'active_profile': 'NOT selected by this view',
                         'approved_alternates': [], 'resume_authorized': False,
                         'reason': 'No physically validated alternate profile is registered here; no camera visual odometry is claimed'}}
