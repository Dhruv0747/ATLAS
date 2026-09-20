"""Non-motion commissioning, reusing the web cache. No actuator/serial access.

Records observations, NOT applied calibration. Hardware-owner leases must be
commissioned separately before enabling actuator tests or calibration writes.
"""
import ast
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import statistics
import threading
import time
import uuid

from atlas_encoder_selection import WHEEL_NAMES
from atlas_commissioning_evidence import EvidenceLedger, observation_gate, readiness


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def item(data, key):
    obj = data.get(key, {})
    return obj if isinstance(obj, dict) else {}


def fresh(data, key, limit=2):
    age = item(data, key).get('age')
    return finite(age) and 0 <= age <= limit


def value(data, key, default=None):
    return item(data, key).get('value', default)


def decoded(data, key):
    raw = value(data, key, {})
    try:
        result = json.loads(raw) if isinstance(raw, str) else raw
        return result if isinstance(result, dict) else {}
    except (ValueError, TypeError):
        return {}


def constants(path):
    """Read literal configuration without importing the hardware driver."""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
    return out


def configuration(root):
    files = ['scripts/yahboom_base.py', 'scripts/atlas_status_web.py',
             'config/encoder_selection.yaml', 'config/atlas_ekf.yaml',
             'config/im10a_mounting.yaml', 'config/im10a_gyro_bias.json',
             'config/steering_calibration.json',
             'systemd/user/atlas-uno-r4-sensor-hub.service.d/camera-home.conf']
    hashes = {}
    for name in files:
        path = root / name
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    base = constants(root / 'scripts/yahboom_base.py')
    steering = {}
    for name in ('front', 'rear'):
        p = name.upper() + '_STEER_'
        steering[name] = {k.lower(): base.get(p+k) for k in ('CENTER','LEFT','RIGHT','SERVO_ID')}
    return {'source_hashes': hashes, 'steering': steering,
            'counts_per_revolution': base.get('ENCODER_COUNTS_PER_REV'),
            'encoder_forward_sign': base.get('ENCODER_FORWARD_SIGN'),
            'wheel_circumference_m': base.get('WHEEL_CIRCUMFERENCE_M'),
            'wheelbase_m': base.get('WHEELBASE_M'), 'motor_locations': list(WHEEL_NAMES),
            'calibration_status': 'CONFIGURED / PHYSICAL REVERIFICATION REQUIRED',
            'warning': 'Encoder scales predate motor replacements. Old motor_config.yaml and encoder YAML locations are NOT authoritative. Runtime overrides require separate verification.',
            'actuator_commissioning_enabled': False,
            'storage_scope': 'Saved test observations only; no active calibration is overwritten.'}


def hardware_check(data):
    checks = []
    def add(name, key, limit=2, warning='', predicate=None):
        live = fresh(data,key,limit)
        valid = live and (predicate is None or predicate(value(data,key)))
        checks.append({'name': name, 'key': key, 'state': ('WARNING' if warning else 'PASS') if valid else 'FAIL',
                       'age_s': item(data,key).get('age'), 'observed_hz': item(data,key).get('observed_hz'),
                       'scope': warning if valid and warning else 'Fresh telemetry only; not physical calibration' if valid else 'Missing, stale or invalid data'})
    add('Motor controller / encoders','encoder_health',2,
        'Stationary packets do not verify encoder direction/count accuracy; inspect exclusions.',
        lambda v: decoded({'x':{'value':v}},'x').get('packet_fresh') is True)
    add('Steering commands','front_steer',2,'PHYSICAL FEEDBACK NOT AVAILABLE')
    add('Rear steering commands','rear_steer',2,'PHYSICAL FEEDBACK NOT AVAILABLE')
    add('Camera video','camera_info',3,predicate=lambda v:isinstance(v,dict) and v.get('bytes',0)>0)
    add('Camera servo controller','camera_servo_status',2,'Pulse reports are not physical position.',lambda v:str(v).startswith('online '))
    add('IM10A','imu_full',2,'Monitoring only; stationary test does not qualify EKF fusion.',lambda v:isinstance(v,dict) and all(finite(v.get(k)) for k in ('gx','gy','gz','ax','ay','az')))
    add('Yahboom IMU','board_imu_heading',2)
    add('LiDAR','lidar',3,predicate=lambda v:isinstance(v,dict) and v.get('points',0)>0)
    add('Radar','radar_decoder_status',2,'Targets are not confirmed people.',lambda v:'state=VALID' in str(v))
    add('BME680','outside_status',5,predicate=lambda v:str(v).startswith('BME680_') and 'OFFLINE' not in str(v))
    add('AMG8833','thermal_status',3,predicate=lambda v:str(v).startswith('online '))
    add('UNO I2C status','i2c_status',8,predicate=lambda v:str(v).startswith('I2CSTAT,'))
    us = str(value(data,'us_status',''))
    for side,code in [('front','F'),('left','L'),('right','R'),('rear','B')]:
        if fresh(data,'us_status',3) and f'{code}=DISABLED' in us:
            checks.append({'name':side+' ultrasonic','state':'NOT TESTED','scope':'Disabled in current MCU status'})
        else:
            add(side+' ultrasonic','us_'+side,3,'Distance accuracy requires a known target.',lambda v:finite(v) and v>0)
    gps = decoded(data,'gps_diagnostics')
    add('GNSS','gps_diagnostics',3,'' if gps.get('fix_valid') else 'NO FIX — not usable for positioning.',lambda v:decoded({'x':{'value':v}},'x').get('transport_open') is True)
    add('Main BMS','bms_json',20,predicate=lambda v:decoded({'x':{'value':v}},'x').get('ok') is True)
    add('INA3221','jetson_power_status',4,predicate=lambda v:str(v).startswith('INA3221_OK'))
    add('Remote input','joy',2)
    return {'state':'ATTENTION REQUIRED' if any(c['state']!='PASS' for c in checks) else 'TELEMETRY PASS',
            'checks':checks,'scope':'Non-motion telemetry check only. No physical calibration PASS is awarded.'}


def distance_result(known_mm, samples):
    if not finite(known_mm) or not 10 <= known_mm <= 10000:
        raise ValueError('Known distance must be 10..10000 mm')
    vals = [v for v in samples if finite(v) and v > 0]
    if len(vals)<3:
        return {'state':'FAIL','reason':'Fewer than three fresh valid echoes','samples':len(vals)}
    measured=statistics.median(vals)
    return {'state':'OBSERVED','known_mm':known_mm,'median_mm':measured,
            'error_mm':measured-known_mm,'error_percent':100*(measured-known_mm)/known_mm,
            'min_mm':min(vals),'max_mm':max(vals),'samples':len(vals),
            'reason':'Comparison only; no offset/scale applied and no universal accuracy threshold assumed.'}


def imu_result(samples, duration=10):
    valid=[(t,v) for t,v in samples if isinstance(v,dict) and all(finite(v.get(k)) for k in ('gx','gy','gz','ax','ay','az'))]
    if len(valid)<20:
        return {'state':'FAIL','reason':'Insufficient fresh IMU observations','samples':len(valid)}
    gaps=[b[0]-a[0] for a,b in zip(valid,valid[1:])]
    span=valid[-1][0]-valid[0][0]
    stats={k:{'mean':statistics.mean(v[k] for _,v in valid),'stddev':statistics.pstdev(v[k] for _,v in valid)} for k in ('gx','gy','gz','ax','ay','az')}
    return {'state':'WARNING','samples':len(valid),'sampled_hz':(len(valid)-1)/span if span>0 else None,
            'max_observed_gap_s':max(gaps),'coverage_s':span,'statistics':stats,
            'reason':'Stationarity is operator-confirmed, not proven. Observe bias/noise; no EKF or sensor calibration changed.',
            'freshness_pass':span>=duration-1 and max(gaps)<.5,
            'units':{'gyro':'rad/s','acceleration':'m/s^2'}}


class Console:
    def __init__(self, root, database, snapshot):
        self.root=Path(root)
        try:
            self.config=configuration(Path(root))
        except (OSError, ValueError, SyntaxError) as exc:
            self.config={'source_hashes':{},'configuration_error':str(exc),
                         'actuator_commissioning_enabled':False}
        self.database=Path(database)
        self.snapshot=snapshot
        self.lock=threading.Lock()
        self.active=None
        self.last=None
        self.last_start=0.
        self.evidence_error=None
        self.ledger=None
        try:
            self.ledger=EvidenceLedger(self.root,self.database)
            self.ledger.import_direction_observation()
            self.ledger.import_configured_exclusion()
        except (OSError, ValueError, sqlite3.Error) as exc:
            self.evidence_error=str(exc)

    def evidence(self):
        if self.evidence_error or self.ledger is None:
            raise ValueError('Evidence storage unavailable; no physical test is authorized')
        with self.lock:
            active_id=self.active.get('id') if self.active else None
        records=self.ledger.current(active_id)
        return {'records':records,'readiness':readiness(records,self.snapshot()),
                'scope':'Evidence/guidance only; actuator configuration and navigation gates are unchanged.'}

    def confirm_steering(self,side,expected_hash,confirmation):
        """Witness an already-saved calibration. No actuator write or motion."""
        if side not in ('front','rear') or not isinstance(confirmation,str) or not 12<=len(confirmation.strip())<=500:
            raise ValueError('Confirm the physical centre and both safe endpoints (12–500 characters)')
        if self.ledger is None or self.evidence_error:
            raise ValueError('Evidence storage unavailable')
        gate='steering_'+side
        sig=self.ledger.signature(gate)
        if expected_hash!=sig['hash']:
            raise ValueError('Configuration changed; reload and review the saved positions')
        data=self.snapshot()
        owner=decoded(data,'steering_calibration')
        policy=decoded(data,'control_policy')
        if not fresh(data,'steering_calibration',1) or not fresh(data,'control_policy',1) or policy.get('stop_latched') is not True:
            raise ValueError('Fresh owner telemetry and latched drive stop required')
        if owner.get('saving') or owner.get('error'):
            raise ValueError('Wait for a successful owner-side save')
        path=self.root/'config/steering_calibration.json'
        if not path.exists():
            raise ValueError('No saved calibration exists; defaults are not physical verification')
        saved=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(saved,dict) or not isinstance(saved.get('steering'),dict):
            raise ValueError('Invalid saved steering configuration')
        points=saved.get('steering',{}).get(side,{})
        if not isinstance(points,dict) or not all(type(points.get(k)) is int for k in ('center','left','right')) or not points['right']<points['center']<points['left']:
            raise ValueError('Saved points are invalid')
        if points!=owner.get('saved',{}).get(side) or not saved.get('saved_at'):
            raise ValueError('Saved file does not match the live owner')
        if self.ledger.signature(gate)!=sig:
            raise ValueError('Calibration changed during review; reload')
        return self.ledger.record(gate,'PASS',{'servo_commands_deg':points,'saved_at':saved['saved_at'],
                    'physical_feedback':'NOT INSTALLED','scope':'Operator-verified safe range, not tyre-angle measurement or ground alignment'},
                    'explicit operator witness + saved file + live owner agreement',confirmation.strip(),sig)

    def history(self):
        if not self.database.exists():
            return []
        with closing(sqlite3.connect(self.database,timeout=1)) as db:
            return [json.loads(r[0]) for r in db.execute('SELECT payload FROM results ORDER BY id DESC LIMIT 100')]

    def save(self,result):
        self.database.parent.mkdir(parents=True,exist_ok=True)
        result={**result,'timestamp_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                'configuration_hashes':self.config['source_hashes'],'physical_calibration_pass':False}
        with closing(sqlite3.connect(self.database,timeout=1)) as db:
            db.execute('CREATE TABLE IF NOT EXISTS results (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('INSERT INTO results(payload) VALUES (?)',(json.dumps(result,allow_nan=False),))
            db.execute('DELETE FROM results WHERE id NOT IN (SELECT id FROM results ORDER BY id DESC LIMIT 500)')
            db.commit()
        gate=observation_gate(result.get('kind'),result.get('side'))
        if gate and self.ledger is not None:
            status='FAIL' if result.get('state')=='FAIL' else 'WARNING' if result.get('state') in ('WARNING','ATTENTION REQUIRED') else 'OBSERVED'
            self.ledger.record(gate,status,result,'bounded cached telemetry observation',
                               signature=result.get('evidence_configuration'))
        return result

    def state(self):
        with self.lock:
            return {'active':dict(self.active) if self.active else None,'last':self.last,
                    'actuator_mode':'Steering uses existing owner lease; individual motor commissioning is not implemented',
                    'calibration_writes_enabled':False}

    def start(self,kind,side=None,known_mm=None):
        if kind not in ('hardware','imu','gnss','distance'):
            raise ValueError('Only non-motion observations are enabled')
        if kind=='distance':
            if side not in ('front','rear','left','right'):
                raise ValueError('Unknown sensor')
            distance_result(known_mm,[])
        with self.lock:
            now=time.monotonic()
            if self.active or now-self.last_start<2:
                raise ValueError('A test is running or cooldown is active')
            self.last_start=now
            self.active={'id':uuid.uuid4().hex,'kind':kind,'side':side,'duration_s':0 if kind=='hardware' else 10,'started_monotonic':now}
            job=dict(self.active)
            try:
                if self.ledger is None or self.evidence_error:
                    raise ValueError('Evidence storage unavailable')
                gate=observation_gate(kind,side)
                job['evidence_configuration']=self.ledger.signature(gate)
                self.ledger.record(gate,'IN_PROGRESS',{'observation_id':job['id']},'bounded cached telemetry observation',
                                   signature=job['evidence_configuration'])
            except Exception:
                self.active=None
                raise
        threading.Thread(target=self._run,args=(job,known_mm),daemon=True).start()
        return job

    def _run(self,job,known_mm):
        try:
            if job['kind']=='hardware':
                result=hardware_check(self.snapshot())
            else:
                key={'imu':'imu_full','gnss':'gps_diagnostics','distance':'us_'+str(job['side'])}[job['kind']]
                samples=[]; previous=None; missing=0; moving=False; yaw=[]; last_yaw=None
                start=time.monotonic()
                while time.monotonic()-start<10:
                    data=self.snapshot(); obj=item(data,key); stamp=obj.get('sample_time')
                    if not fresh(data,key,2) or not finite(stamp):
                        missing+=1
                    elif stamp!=previous:
                        samples.append((time.monotonic()-start,obj.get('value'))); previous=stamp
                    y=item(data,'imu_yaw')
                    if fresh(data,'imu_yaw',1) and finite(y.get('value')) and y.get('sample_time')!=last_yaw:
                        yaw.append(y['value']);last_yaw=y.get('sample_time')
                    cmd=value(data,'cmd_vel',{}) or {}; od=value(data,'odom',{}) or {}
                    moving |= any(finite(v) and abs(v)>.02 for v in (cmd.get('lin'),cmd.get('ang'),od.get('vx'),od.get('wz')))
                    time.sleep(.1)
                if job['kind']=='imu':
                    result=imu_result(samples)
                    result['yaw_change_deg']=sum((b-a+180)%360-180 for a,b in zip(yaw,yaw[1:])) if len(yaw)>1 else None
                    result['yaw_note']='Sensor heading only; not navigation yaw or validated magnetic heading.'
                elif job['kind']=='distance':
                    result=distance_result(known_mm,[v for _,v in samples])
                else:
                    fixes=[decoded({'x':{'value':v}},'x') for _,v in samples]
                    result={'state':'WARNING','samples':len(fixes),'valid_fix_samples':sum(v.get('fix_valid') is True for v in fixes),
                            'last':fixes[-1] if fixes else {},'reason':'GNSS observation, not position accuracy validation; no indoor fix assumed.'}
                result['stale_poll_samples']=missing
                if missing or moving:
                    result.update(state='FAIL' if missing else 'WARNING',reason='Stale data or nonzero motion during stationary observation',motion_observed=moving)
            result=self.save({**job,**result})
        except Exception as exc:
            result={**job,'state':'FAIL','reason':str(exc),'physical_calibration_pass':False}
            if self.ledger is not None:
                try:
                    self.ledger.record(observation_gate(job['kind'],job.get('side')),'FAIL',result,
                                       'observation failed; no qualification granted',
                                       signature=job.get('evidence_configuration'))
                except Exception:
                    self.evidence_error='Evidence persistence failed; repair storage before testing'
        with self.lock:
            self.last=result;self.active=None
