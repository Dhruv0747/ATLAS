#!/usr/bin/env python3
"""ATLAS Stage 28: supervised, transactional deployment of the read-only FlySky RC bridge.

PROPOSAL. Every mutating action refuses unless OWNER_APPROVED=yes and the owner's explicit flags are given.
Two separately approvable stages, each with its own backup, verification and rollback:

  A  install-recovery : install atlas_base_maintenance.py + additive base-hold patch of atlas_sensor_recovery.py,
                        restart ONLY atlas-sensor-recovery, prove the running recovery honours a lease
                        (short HOLD lease, ack, release) WITHOUT touching the base.
  B  deploy           : arm a base-only lease, install a RUNTIME ExecCondition drop-in (tmpfs), wait for the
                        recovery ack, install the 4 reviewed files, authorise exactly ONE start, restart ONLY
                        rover-base-telemetry, verify telemetry, /atlas/rc/frames publisher, safety, CPU/RAM/temp,
                        protected services; release. Any failure after the file install -> rollback-bridge
                        (restore originals, at most one authorised rollback start). A failed rollback stops,
                        keeps the fail-closed hold and reports; it never loops.

Never: flashing, serial access, motor/servo commands, E-STOP/arbitration/Nav2/TF/localization changes,
threshold changes, disabling recovery, automatic retries. The 75 % CPU / 80 % RAM / 70 C limits are unchanged;
--cpu-rule only selects how a restart transient is judged (owner decision, no default):
strict = every sample <= 75 from the restart; transient = >75 tolerated only within an explicit, evidence-based bound,
every sample reported, RAM/temp strict throughout, safety sampled during the window.

Run detached from SSH so a dropped session cannot orphan the lease, e.g.
  systemd-run --user --unit=atlas-stage28-deploy --collect --wait --pipe \
     -E OWNER_APPROVED=yes python3 deploy_rc_bridge.py deploy --cpu-rule strict ...
"""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request

HERE = Path(__file__).resolve().parent
REPO_SCRIPTS = HERE.parents[2] / 'scripts'
RC_TOOLS = HERE.parent / 'stage28_yahboom_rc'
MANIFEST = json.loads((HERE / 'MANIFEST.json').read_text())
CPU_LIMIT, RAM_LIMIT, TEMP_LIMIT = 75.0, 80.0, 70.0          # unchanged ATLAS limits
MAX_TRANSIENT_BOUND_S = 30.0   # hard ceiling for --transient-bound-s (evidence: longest measured node restart 26 s)
GOOD_ENCODER_STATES = {'READY', 'HEALTHY', 'DEGRADED'}


class Fail(RuntimeError):
    """A gate failed. Carries the stage so the caller knows what to undo."""


# ------------------------------------------------------------------ environment (tests override)
class Env:
    def __init__(self, **kw):
        uid = os.getuid()
        self.scripts = Path('/home/jetson/project_atlas/scripts')
        self.api = 'http://127.0.0.1:8088'
        self.evidence_root = Path('/home/jetson/project-atlas-migration')
        self.base = 'rover-base-telemetry.service'
        self.recovery = 'atlas-sensor-recovery.service'
        self.protected = ['atlas-cmd-vel-mux.service', 'atlas-safety-status.service', 'atlas-camera.service',
                          'atlas-ekf.service', 'atlas-localization.service', 'atlas-lidar.service',
                          'atlas-voice-companion.service', 'rover-status-web.service', 'atlas-camera-joystick.service',
                          'atlas-mode-manager.service', 'atlas-tight-recovery.service']
        self.dropin_dir = Path(f'/run/user/{uid}/systemd/user/{self.base}.d')
        self.dropin_name = '90-atlas-base-maintenance.conf'
        self.python = '/usr/bin/python3'
        self.thermal_root = '/sys/class/thermal'
        self.maint_root = None
        self.lease_s = 480.0
        self.preflight_s = 30
        self.pre_restart_s = 10
        self.steady_s = 30
        self.ack_timeout_s = 8.0
        self.in_flight_wait_s = 40.0
        self.ready_timeout_s = 60.0
        self.telemetry_timeout_s = 30.0
        self.rc_publisher_timeout_s = 20.0
        self.recovery_ready_timeout_s = 60.0
        self.ready_re = r'Yahboom board ready on \S+, firmware=3\.6, car_type=5'
        self.sleep = time.sleep
        self.__dict__.update(kw)

    # system access, each overridable
    def systemctl(self, *args, timeout=30, check=True):
        return subprocess.run(['systemctl', '--user', *args], capture_output=True, text=True,
                              timeout=timeout, check=check)

    def journal(self, invocation, since_epoch=0.0):
        """Messages of exactly one unit invocation (includes its ExecCondition gate line), newest last."""
        if not invocation:
            return ''
        r = subprocess.run(['journalctl', '--user', f'_SYSTEMD_INVOCATION_ID={invocation}', '-o', 'json',
                            '--no-pager'], capture_output=True, text=True, timeout=15)
        out = []
        for line in r.stdout.splitlines():
            with contextlib.suppress(ValueError, KeyError, TypeError):
                d = json.loads(line)
                if int(d['__REALTIME_TIMESTAMP']) / 1e6 >= since_epoch:
                    out.append(str(d.get('MESSAGE', '')))
        return '\n'.join(out)

    def get(self, path):
        with urllib.request.urlopen(self.api + path, timeout=2) as r:
            return json.load(r)

    def cpu_samples(self, n):
        """n whole-machine busy % over consecutive 1-s windows (/proc/stat; top's first frame is not used)."""
        def rd():
            v = [int(x) for x in open('/proc/stat').readline().split()[1:9]]
            return sum(v), v[3] + v[4]
        out, prev = [], rd()
        for _ in range(n):
            time.sleep(1.0)
            cur = rd()
            dt = cur[0] - prev[0]
            out.append(round(100.0 * (dt - (cur[1] - prev[1])) / dt, 2) if dt > 0 else 100.0)
            prev = cur
        return out

    def ram_temp(self):
        mem = {}
        for line in open('/proc/meminfo'):
            k, v = line.split(':', 1)
            mem[k] = int(v.split()[0])
        ram = 100.0 * (mem['MemTotal'] - mem['MemAvailable']) / mem['MemTotal']
        temps = {}
        for z in sorted(Path(self.thermal_root).glob('thermal_zone*')):
            c, name = read_zone(z)
            if c is not None:
                temps[name] = c
        return round(ram, 2), temps


def read_zone(z):
    """(celsius, type) or (None, type). Jetson CV zones answer EAGAIN; Python 3.10's buffered text read then fails
    with TypeError instead of OSError. Any failure or implausible value = not applicable, never 0 C."""
    try:
        fd = os.open(z / 'temp', os.O_RDONLY | os.O_NONBLOCK)
        try:
            raw = os.read(fd, 32)
        finally:
            os.close(fd)
        c = int(raw.decode().strip()) / 1000.0
        name = (z / 'type').read_bytes().decode(errors='replace').strip() or z.name
    except Exception:
        return None, z.name
    return (c if 0.0 < c <= 150.0 else None), name


# ------------------------------------------------------------------ evidence
class Evidence:
    def __init__(self, env, kind):
        self.dir = env.evidence_root / f'stage28-{kind}-{time.strftime("%Y%m%d_%H%M%S")}-{time.time_ns() % 10**9:09d}'
        self.dir.mkdir(parents=True, exist_ok=False)
        self.n = 0

    def log(self, msg):
        line = f'{time.strftime("%H:%M:%S")} {msg}'
        print(line, flush=True)
        with open(self.dir / 'log.txt', 'a') as f:
            f.write(line + '\n')

    def save(self, name, obj):
        self.n += 1
        p = self.dir / f'{self.n:03d}-{name}.json'
        p.write_text(json.dumps(obj, indent=1, default=str))
        return p

    def seal(self):
        rows = []
        for p in sorted(self.dir.rglob('*')):
            if p.is_file() and p.name != 'SHA256SUMS.all':
                rows.append(f'{sha(p)}  {p.relative_to(self.dir)}')
        (self.dir / 'SHA256SUMS.all').write_text('\n'.join(rows) + '\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ------------------------------------------------------------------ gates
def safety_snapshot(env):
    """Per-predicate evidence from the status web (independent of atlas-sensor-recovery's own stop guard)."""
    raw, pred = {}, {}
    try:
        est = env.get('/api/estop/state')
        raw['estop'] = est
        pred['estop_latched'] = est.get('latched') is True
    except Exception as exc:
        raw['estop_error'] = repr(exc)
        pred['estop_latched'] = False
    encs, eh = None, {}
    try:
        r = env.get('/api/status')['ros']
    except Exception as exc:
        raw['status_error'] = repr(exc)
        r = {}

    def item(k):
        v = r.get(k) or {}
        raw[k] = v
        age = v.get('age')
        fresh = type(age) in (int, float) and 0 <= age <= 1.0
        return v.get('value'), fresh

    def js(x):
        return json.loads(x) if isinstance(x, str) else (x or {})
    try:
        pol, f = item('control_policy'); pol = js(pol)
        pred.update(policy_fresh=f, stop_latched=pol.get('stop_latched') is True,
                    manual_only=pol.get('manual_only') is True, commission_off=pol.get('commission_armed') is False,
                    source_stopped=pol.get('source') == 'STOPPED')
        cmd, f = item('cmd_vel')
        pred['cmd_fresh'] = f
        pred['cmd_zero'] = isinstance(cmd, dict) and all(type(cmd.get(k)) in (int, float) and cmd[k] == 0
                                                         for k in ('lin', 'ang'))
        ms, f = item('motor_speed')
        pred['motor_output_zero'] = f and type(ms) in (int, float) and ms == 0
        wd, _ = item('web_drive')
        pred['web_drive_stop'] = wd == 'STOP'
        dp, _ = item('drive_pid')
        pred['drive_pid_inactive'] = js(dp).get('active') is False
        od, f = item('odom')
        pred['odom_still'] = f and isinstance(od, dict) and all(
            type(od.get(k)) in (int, float) and abs(od[k]) < 1e-3 for k in ('vx', 'wz'))
        encs = []
        for k in ('enc_m1', 'enc_m2', 'enc_m3', 'enc_m4'):
            v, f = item(k)
            encs.append(v if f and type(v) is int else None)
        pred['encoders_fresh'] = None not in encs
        eh, f = item('encoder_health'); eh = js(eh)
        pred['telemetry_live'] = (f and str(eh.get('state', '')).upper() in GOOD_ENCODER_STATES
                                  and eh.get('packet_fresh') is True
                                  and type(eh.get('packet_age_s')) in (int, float) and 0 <= eh['packet_age_s'] <= 1)
    except Exception as exc:
        raw['parse_error'] = repr(exc)
        pred['parse_ok'] = False
    return {'ok': bool(pred) and all(pred.values()), 'predicates': pred, 'encoders': encs,
            'packets': eh.get('serial_encoder_packets') if isinstance(eh, dict) else None,
            'raw': raw, 'wall': time.time()}


def require_safe(env, ev, label, count=3, spacing=2.0):
    """count snapshots; every predicate true; encoders unchanged; packet counter strictly increasing."""
    snaps = []
    for i in range(count):
        if i:
            env.sleep(spacing)
        s = safety_snapshot(env)
        ev.save(f'safety-{label}-{i}', s)          # retained BEFORE the decision
        snaps.append(s)
        if not s['ok']:
            bad = [k for k, v in s['predicates'].items() if not v]
            raise Fail(f'{label}: safety predicate(s) failed: {bad}')
    if any(s['encoders'] != snaps[0]['encoders'] for s in snaps):
        raise Fail(f'{label}: encoder counts changed (motion) {[s["encoders"] for s in snaps]}')
    pk = [s['packets'] for s in snaps]
    if not all(type(p) is int for p in pk) or any(b <= a for a, b in zip(pk, pk[1:])):
        raise Fail(f'{label}: serial packet counter not progressing {pk}')
    ev.log(f'{label}: safety OK x{count}; encoders {snaps[0]["encoders"]}; packets {pk}')
    return snaps


def resources_strict(env, ev, label, seconds):
    cpu = env.cpu_samples(seconds)
    ram, temps = env.ram_temp()
    rec = {'label': label, 'cpu_1s': cpu, 'cpu_max': max(cpu), 'cpu_mean': round(sum(cpu) / len(cpu), 2),
           'ram_pct': ram, 'temps_c': temps, 'temp_max_c': max(temps.values()) if temps else None}
    ev.save(f'resources-{label}', rec)
    if not temps:
        raise Fail(f'{label}: no trustworthy temperature reading')
    if rec['cpu_max'] > CPU_LIMIT or ram > RAM_LIMIT or rec['temp_max_c'] >= TEMP_LIMIT:
        raise Fail(f'{label}: resources over limit cpu_max={rec["cpu_max"]} ram={ram} temp={rec["temp_max_c"]}')
    ev.log(f'{label}: resources OK cpu mean {rec["cpu_mean"]} max {rec["cpu_max"]} ram {ram} temp {rec["temp_max_c"]}')
    return rec


class CpuRecorder:
    """Continuous 1-s whole-machine CPU + RAM + temperature samples in a background thread, started BEFORE a restart
    so the restart second itself is measured. Nothing is averaged away: every sample is kept, saved and reported."""

    def __init__(self, env):
        self.env, self.samples, self.rt, self._stop = env, [], [], threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._t.join(timeout=5)

    def _run(self):
        while not self._stop.is_set():
            t0 = time.time()
            x = self.env.cpu_samples(1)[0]
            if time.time() - t0 < 0.5:          # scripted samplers return instantly: keep a 1-s cadence
                self._stop.wait(1.0)
            now = time.time()
            self.samples.append((now, x))
            try:
                ram, temps = self.env.ram_temp()
                self.rt.append((now, ram, max(temps.values()) if temps else None))
            except Exception as exc:              # an unreadable sample is evidence, never a pass
                self.rt.append((now, None, f'error {exc!r}'))

    def since(self, t):
        return [x for (ts, x) in list(self.samples) if ts > t]

    def timed_since(self, t):
        return [(round(ts - t, 2), x) for (ts, x) in list(self.samples) if ts > t]


# Predicates that do not depend on the restarted base itself (used while the base is down by design in stage B).
NON_BASE_PREDICATES = ('estop_latched', 'policy_fresh', 'stop_latched', 'manual_only', 'commission_off',
                       'source_stopped', 'cmd_fresh', 'cmd_zero', 'web_drive_stop', 'drive_pid_inactive')


class SafetyRecorder:
    """Safety snapshots every ~1.5 s through the whole transient window; every snapshot is saved."""

    def __init__(self, env, required=None, period=1.5):
        self.env, self.required, self.period = env, required, period
        self.snaps, self._stop = [], threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._t.join(timeout=10)

    def _run(self):
        while not self._stop.is_set():
            try:
                s = safety_snapshot(self.env)
            except Exception as exc:
                s = {'ok': False, 'predicates': {'snapshot': False}, 'error': repr(exc), 'wall': time.time()}
            keys = self.required or list(s['predicates'])
            s['window_ok'] = all(s['predicates'].get(k) is True for k in keys)
            self.snaps.append(s)
            self._stop.wait(self.period)

    def failures(self, t0, t1):
        return [{'t': round(s['wall'] - t0, 2), 'failed': [k for k, v in s['predicates'].items() if not v]}
                for s in list(self.snaps) if t0 <= s['wall'] <= t1 and not s['window_ok']]


SAFETY_MAX_GAP_S = 3.5          # snapshots every ~1.5 s; a larger gap means monitoring is not operating reliably


def early_abort(env, ev, label, rec, t_restart, bound_s, safety):
    """Checked every 0.5 s during the window: any safety failure, unreliable safety monitoring, RAM/temperature
    violation, or CPU > 75 % after the bound aborts at once (the caller rolls back)."""
    timed = rec.timed_since(t_restart)
    now = t_restart + (timed[-1][0] if timed else 0.0)     # same clock as the recorder
    why = []
    if safety is not None:
        fails = safety.failures(t_restart, now)
        if fails:
            why.append(f'safety failure {fails[:3]}')
        walls = [t_restart] + [x['wall'] for x in list(safety.snaps) if t_restart < x['wall'] <= now] + [now]
        gap = max(b - a for a, b in zip(walls, walls[1:]))
        if gap > SAFETY_MAX_GAP_S:
            why.append(f'safety monitoring not operating reliably (gap {gap:.1f} s > {SAFETY_MAX_GAP_S} s)')
    for ts, ram, temp in list(rec.rt):
        if ts > t_restart and not (type(ram) in (int, float) and ram <= RAM_LIMIT and
                                   type(temp) in (int, float) and temp < TEMP_LIMIT):
            why.append(f'RAM/temperature sample at +{ts - t_restart:.1f} s: ram={ram} temp={temp}')
            break
    late = [(d, x) for d, x in timed if d > bound_s and x > CPU_LIMIT]
    if late:
        why.append(f'CPU > {CPU_LIMIT} after the {bound_s} s bound: {late}')
    if why:
        ev.save(f'abort-{label}', {'t_restart': t_restart, 'reasons': why,
                                   'cpu_samples_since_restart': rec.timed_since(t_restart),
                                   'safety_snapshots': list(safety.snaps) if safety else []})
        raise Fail(f'{label}: IMMEDIATE ABORT: ' + '; '.join(why))


def resources_after_restart(env, ev, label, rule, rec, t_restart, bound_s=None, safety=None):
    """Judged on the continuous recorder from the restart moment on (first post-restart seconds included).

    strict    : every CPU sample <= 75 for steady_s seconds after the restart.
    transient : CPU samples > 75 are tolerated ONLY in (t_restart, t_restart + bound_s]; every such sample is
                labelled and reported. Afterwards a strict window of steady_s seconds. Any sample > 75 after the
                bound fails. RAM <= 80 and temperature < 70 are strict on EVERY sample, inside the window too.
                Safety snapshots must hold throughout the window (when a SafetyRecorder is given).
    Limits never change."""
    if rule == 'strict':
        bound_s = 0.0
    elif rule != 'transient' or bound_s is None or not 0 < bound_s <= MAX_TRANSIENT_BOUND_S:
        raise Fail(f'{label}: transient rule requires an explicit bound 0 < bound <= {MAX_TRANSIENT_BOUND_S} s')
    while len([d for d, _ in rec.timed_since(t_restart) if d > bound_s]) < env.steady_s:
        early_abort(env, ev, label, rec, t_restart, bound_s, safety)       # immediate, not at window end
        env.sleep(0.5)
    early_abort(env, ev, label, rec, t_restart, bound_s, safety)
    timed = rec.timed_since(t_restart)
    inside = [(d, x) for d, x in timed if d <= bound_s]
    after = [(d, x) for d, x in timed if d > bound_s]
    rt = [(round(ts - t_restart, 2), ram, temp) for ts, ram, temp in list(rec.rt) if ts > t_restart]
    bad_rt = [r for r in rt if not (type(r[1]) in (int, float) and r[1] <= RAM_LIMIT and
                                     type(r[2]) in (int, float) and r[2] < TEMP_LIMIT)]
    over_inside = [(d, x) for d, x in inside if x > CPU_LIMIT]
    over_after = [(d, x) for d, x in after if x > CPU_LIMIT]
    safety_fail = safety.failures(t_restart, t_restart + bound_s + env.steady_s) if safety else []
    report = {'label': label, 'rule': rule, 'bound_s': bound_s, 'limits': [CPU_LIMIT, RAM_LIMIT, TEMP_LIMIT],
              'cpu_samples_since_restart': timed,
              'over_limit_inside_bound': over_inside, 'over_limit_after_bound': over_after,
              'last_over_limit_s': max([d for d, x in timed if x > CPU_LIMIT], default=None),
              'ram_temp_samples': rt, 'ram_temp_violations': bad_rt,
              'safety_snapshots_in_window': len(safety.snaps) if safety else 0, 'safety_failures': safety_fail}
    ev.save(f'resources-{label}-{rule}', report)
    if over_inside:
        ev.log(f'{label}: TRANSIENT over-limit CPU samples inside the {bound_s} s bound (reported, not hidden): {over_inside}')
    if over_after or bad_rt or safety_fail or (rule == 'strict' and over_inside):
        raise Fail(f'{label}: {rule.upper()} gate failed: cpu>75 after bound {over_after or over_inside}, '
                   f'ram/temp violations {bad_rt[:3]}, safety failures {safety_fail[:3]}')
    ev.log(f'{label}: {rule.upper()} OK: {len(over_inside)} over-limit samples within {bound_s} s (last '
           f'{report["last_over_limit_s"]} s); {len(after)} samples after bound all <= {CPU_LIMIT}; RAM/temp OK every sample')
    return report


# ------------------------------------------------------------------ systemd helpers
def unit_state(env, unit):
    out = env.systemctl('show', unit, '-p', 'ActiveState', '-p', 'SubState', '-p', 'MainPID', '-p', 'NRestarts',
                        '-p', 'InvocationID', '-p', 'DropInPaths', '-p', 'ExecMainStartTimestampMonotonic').stdout
    return dict(line.split('=', 1) for line in out.splitlines() if '=' in line)


def no_jobs(env, unit):
    out = env.systemctl('list-jobs', '--no-legend', '--no-pager', check=False).stdout
    return not any(unit in line.split() for line in out.splitlines())


def require_running(env, unit):
    s = unit_state(env, unit)
    if s.get('ActiveState') != 'active' or s.get('SubState') != 'running' or int(s.get('MainPID', '0')) <= 0:
        raise Fail(f'{unit} not active/running: {s}')
    if not no_jobs(env, unit):
        raise Fail(f'{unit} has a queued systemd job')
    return s


def wait_quiescent(env, unit, timeout=20.0):
    """No pending systemd job and not inside an auto-restart wait: safe to authorise a start token."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        s = unit_state(env, unit)
        settled = (s.get('SubState') == 'running' and s.get('ActiveState') == 'active') or \
            s.get('ActiveState') in ('inactive', 'failed')
        if settled and s.get('SubState') != 'auto-restart' and no_jobs(env, unit):
            return s
        env.sleep(0.5)
    raise Fail(f'{unit} did not become quiescent (pending restart/job); not authorising another start')


def identities(env, units):
    return {u: (unit_state(env, u).get('MainPID'), unit_state(env, u).get('ActiveState')) for u in units}


# ------------------------------------------------------------------ files
def install_atomic(src_bytes, dst, mode):
    tmp = dst.with_name(f'.{dst.name}.stage28.tmp')
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as f:
        f.write(src_bytes)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, mode)
    os.replace(tmp, dst)
    dfd = os.open(dst.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def run_insert(script, text):
    """Apply a reviewed insert script to a staged copy; returns the patched text."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / 'target.py'
        p.write_text(text, encoding='utf-8')
        subprocess.run([sys.executable, '-I', str(script), str(p)], check=True, capture_output=True, timeout=30)
        return p.read_text(encoding='utf-8')


def backup(env, ev, names):
    bk = ev.dir / 'backup'
    bk.mkdir()
    meta = {}
    for n in names:
        p = env.scripts / n
        if p.exists():
            shutil.copy2(p, bk / n)
            st = os.stat(p)
            meta[n] = {'present': True, 'sha256': sha(p), 'mode': stat.S_IMODE(st.st_mode), 'uid': st.st_uid}
            if sha(bk / n) != meta[n]['sha256']:
                raise Fail(f'backup verification failed for {n}')
        else:
            meta[n] = {'present': False}
    (bk / 'meta.json').write_text(json.dumps(meta, indent=1))
    with tarfile.open(ev.dir / 'backup.tar', 'w') as t:
        t.add(bk, arcname='backup')
    ev.log(f'backup {bk} ' + json.dumps({k: v.get('sha256', 'absent')[:12] for k, v in meta.items()}))
    return meta


def restore(env, ev, meta):
    bk = ev.dir / 'backup'
    for n, m in meta.items():
        dst = env.scripts / n
        if m['present']:
            install_atomic((bk / n).read_bytes(), dst, m['mode'])
            if sha(dst) != m['sha256']:
                raise Fail(f'restore hash mismatch {n}')
        elif dst.exists():
            dst.unlink()
    ev.log('restored originals: ' + ', '.join(f'{n}={"restored" if m["present"] else "removed"}' for n, m in meta.items()))


# ------------------------------------------------------------------ package
def candidate_files(env, stage):
    """Build the exact stage candidates from the live baselines + reviewed insert scripts; verify every hash."""
    out = {}
    for name, spec in MANIFEST['modified'].items():
        if spec['stage'] != stage:
            continue
        live = env.scripts / name
        if sha(live) != spec['baseline_sha256']:
            raise Fail(f'{name}: live hash {sha(live)} != reviewed baseline {spec["baseline_sha256"]}')
        text = run_insert(HERE / spec['insert'] if spec['insert'].startswith('insert_recovery') else RC_TOOLS / spec['insert'],
                          live.read_text(encoding='utf-8'))
        data = text.encode('utf-8')
        if hashlib.sha256(data).hexdigest() != spec['candidate_sha256']:
            raise Fail(f'{name}: rebuilt candidate hash mismatch')
        out[name] = data
    for name, spec in MANIFEST['added'].items():
        if spec['stage'] != stage:
            continue
        data = (REPO_SCRIPTS / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != spec['sha256']:
            raise Fail(f'{name}: package file hash mismatch')
        dst = env.scripts / name
        if dst.exists() and sha(dst) != spec['sha256']:
            raise Fail(f'{name}: a different file already exists at the destination')
        out[name] = data
    for name, digest in MANIFEST['must_remain'].items():
        if sha(env.scripts / name) != digest:
            raise Fail(f'{name}: shared file changed; it is not replaced by this package')
    return out


def compile_staged(env, files):
    """Byte-compile every candidate and import the pure helpers from a private staging copy (no ROS, no serial)."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        for n in list(MANIFEST['must_remain']) + ['atlas_usb_identity.py']:
            if (env.scripts / n).exists():
                shutil.copy(env.scripts / n, Path(d) / n)
        for n, data in files.items():
            (Path(d) / n).write_bytes(data)
        pure = [n[:-3] for n in files if n in ('atlas_base_maintenance.py', 'atlas_yahboom_rc_report.py',
                                               'atlas_rc_readonly_bridge.py')]
        code = ('import sys, py_compile, importlib\n'
                'd = sys.argv[1]; sys.path.insert(0, d); sys.dont_write_bytecode = True\n'
                'for p in sys.argv[2].split(","):\n'
                '    py_compile.compile(d + "/" + p, cfile=d + "/" + p + ".chk", doraise=True)\n'
                'for m in filter(None, sys.argv[3].split(",")):\n'
                '    importlib.import_module(m)\n')
        subprocess.run([sys.executable, '-I', '-c', code, d, ','.join(files), ','.join(pure)],
                       check=True, capture_output=True, timeout=60)


def selected(files, names):
    return {n: files[n] for n in names}


# ------------------------------------------------------------------ maintenance helpers
def maint(env):
    sys.path.insert(0, str(env.scripts))
    import atlas_base_maintenance as bm
    return bm, bm.Maintenance(root=env.maint_root)


def arm_or_fail(bm, m, purpose, seconds, wait_s):
    try:
        return m.arm(purpose, seconds, wait_s=wait_s)
    except bm.Refused as exc:
        raise Fail(f'maintenance not entered ({exc}); a recovery-owned base attempt may be in flight') from exc


def wait_ack(env, ev, m, session, recovery_pid):
    t0 = time.monotonic()
    first = None
    while time.monotonic() - t0 < env.in_flight_wait_s:
        a = m.read_ack()
        if a and a.get('session') == session:
            first = first or a
            if a.get('recovery_pid') != recovery_pid:
                raise Fail(f'ack from unexpected recovery pid {a.get("recovery_pid")} (expected {recovery_pid})')
            if not a.get('in_flight'):
                ev.save('ack', a)
                ev.log(f'recovery ack: session {session[:8]} pid {recovery_pid} in_flight False after {time.monotonic() - t0:.1f}s')
                return a
        elif time.monotonic() - t0 > env.ack_timeout_s and first is None:
            raise Fail('running recovery did not acknowledge the lease (module not loaded or recovery stalled)')
        env.sleep(0.25)
    raise Fail('a recovery-owned base restart stayed in flight; maintenance not entered')


def dropin_install(env):
    env.dropin_dir.mkdir(parents=True, exist_ok=True)
    gate = f'{env.python} -I {env.scripts}/atlas_base_maintenance.py start-gate'
    (env.dropin_dir / env.dropin_name).write_text(
        '# ATLAS Stage 28 runtime-only maintenance gate (tmpfs; removed on release; gone after reboot)\n'
        f'[Service]\nExecCondition={gate}\n')
    env.systemctl('daemon-reload', timeout=60)
    s = unit_state(env, env.base)
    if str(env.dropin_dir / env.dropin_name) not in s.get('DropInPaths', ''):
        raise Fail('runtime drop-in not loaded by systemd')


def dropin_remove(env):
    p = env.dropin_dir / env.dropin_name
    with contextlib.suppress(FileNotFoundError):
        p.unlink()
    env.systemctl('daemon-reload', timeout=60)
    if str(p) in unit_state(env, env.base).get('DropInPaths', ''):
        raise Fail('runtime drop-in still loaded after removal')


def recovery_base_restarts(env, invocation, since):
    """Lines where the running recovery itself started a base restart since `since`."""
    log = env.journal(invocation, since)
    return [line for line in log.splitlines() if re.search(r'RECOVERING: .*restarting ' + re.escape(env.base), line)]


def wait_recovery_ready(env, rec_before):
    """After a recovery restart: new invocation reporting READY (+ coordination loaded when expected)."""
    deadline = time.monotonic() + env.recovery_ready_timeout_s
    while time.monotonic() < deadline:
        s = unit_state(env, env.recovery)
        if s.get('InvocationID') and s.get('InvocationID') != rec_before.get('InvocationID'):
            log = env.journal(s['InvocationID'])
            if 'READY: full bounded fault recovery armed' in log:
                return s, log
        env.sleep(1)
    raise Fail('restarted recovery did not report READY')


# ------------------------------------------------------------------ stage A
def install_recovery(env, args, ev=None):
    ev = ev or Evidence(env, 'recovery-coordination')
    ev.log('stage A: install base-maintenance coordination into atlas-sensor-recovery (base untouched)')
    names = ['atlas_base_maintenance.py', 'atlas_sensor_recovery.py']
    if sha(env.scripts / 'atlas_sensor_recovery.py') == MANIFEST['modified']['atlas_sensor_recovery.py']['candidate_sha256']:
        raise Fail('coordination already installed')
    mine = selected(candidate_files(env, 'A'), names)
    compile_staged(env, mine)
    require_safe(env, ev, 'A-pre')
    resources_strict(env, ev, 'A-pre', env.preflight_s)
    base0 = require_running(env, env.base)
    rec0 = require_running(env, env.recovery)
    prot0 = identities(env, env.protected)
    meta = backup(env, ev, names)
    try:
        install_atomic(mine['atlas_base_maintenance.py'], env.scripts / 'atlas_base_maintenance.py', 0o644)
        install_atomic(mine['atlas_sensor_recovery.py'], env.scripts / 'atlas_sensor_recovery.py',
                       meta['atlas_sensor_recovery.py']['mode'])
        with CpuRecorder(env) as cpu, SafetyRecorder(env) as safe:
            env.sleep(2.5)                                  # recorders running before the restart
            t0 = time.time()
            ev.log('restarting atlas-sensor-recovery ONLY')
            env.systemctl('restart', env.recovery, timeout=30)
            try:
                rec1, log = wait_recovery_ready(env, rec0)
                if 'ATLAS base maintenance coordination: loaded' not in log:
                    raise Fail('patched recovery did not report coordination loaded')
                rec1 = require_running(env, env.recovery)
                resources_after_restart(env, ev, 'A-post', args.cpu_rule, cpu, t0, args.transient_bound_s, safe)
            finally:
                ev.save('cpu-recorder-A', {'t_restart': t0, 'samples': cpu.samples, 'ram_temp': cpu.rt})
                ev.save('safety-recorder-A', {'t_restart': t0, 'snapshots': safe.snaps})
        # functional proof with the base untouched: short HOLD lease -> ack -> release
        bm, m = maint(env)
        session = arm_or_fail(bm, m, 'stage A functional check (no base restart)', 30.0, env.in_flight_wait_s)
        try:
            wait_ack(env, ev, m, session, int(rec1['MainPID']))
        finally:
            m.release(session)
            m.clear(session)
        require_safe(env, ev, 'A-post')
        if unit_state(env, env.base).get('MainPID') != base0['MainPID']:
            raise Fail('base MainPID changed during stage A')
        if identities(env, env.protected) != prot0:
            raise Fail('a protected service identity changed during stage A')
        bad = recovery_base_restarts(env, rec1['InvocationID'], t0)
        if bad:
            raise Fail(f'recovery restarted the base during stage A: {bad}')
    except Exception as exc:
        ev.log(f'STAGE A FAILED: {exc!r}; rolling back recovery (one recovery restart)')
        ev.save('result', {'result': 'FAIL', 'stage': 'A', 'error': repr(exc)})
        _rollback_recovery_files(env, ev, meta, unit_state(env, env.recovery))
        ev.seal()
        return 1
    ev.save('result', {'result': 'PASS', 'stage': 'A', 'recovery_pid': rec1['MainPID'], 'base_pid': base0['MainPID'],
                       'hashes': {n: sha(env.scripts / n) for n in names}})
    ev.log('STAGE A PASS: recovery honours base maintenance; base not restarted')
    ev.seal()
    return 0


def record_rollback_cpu(env, ev, label, cpu, t):
    """Rollback restarts are not aborted on CPU (restoring the original is the safe direction), but every sample is
    recorded and the over-limit ones are reported."""
    deadline = time.monotonic() + env.steady_s + 15
    while len(cpu.since(t)) < env.steady_s and time.monotonic() < deadline:
        env.sleep(0.5)
    timed = cpu.timed_since(t)
    over = [(d, x) for d, x in timed if x > CPU_LIMIT]
    ev.save(f'cpu-rollback-{label}', {'t_restart': t, 'samples': timed, 'over_limit': over, 'ram_temp': cpu.rt})
    ev.log(f'rollback {label}: {len(over)} CPU samples > {CPU_LIMIT} % (reported): {over}')


def _rollback_recovery_files(env, ev, meta, rec_before):
    try:
        restore(env, ev, meta)
        with CpuRecorder(env) as cpu:
            env.sleep(1.5)
            t = time.time()
            env.systemctl('restart', env.recovery, timeout=30)
            wait_recovery_ready(env, rec_before)
            ev.log('recovery rollback verified: original restored, READY')
            record_rollback_cpu(env, ev, 'A', cpu, t)
    except Exception as exc:
        ev.log(f'RECOVERY ROLLBACK NOT CONFIRMED ({exc!r}): owner inspection required (no further restart attempted)')


# ------------------------------------------------------------------ stage B
def deploy(env, args, ev=None):
    ev = ev or Evidence(env, 'rc-bridge')
    ev.log('stage B: deploy read-only RC bridge under base maintenance')
    if sha(env.scripts / 'atlas_sensor_recovery.py') != MANIFEST['modified']['atlas_sensor_recovery.py']['candidate_sha256']:
        raise Fail('stage A (recovery coordination) is not installed')
    if sha(env.scripts / 'atlas_base_maintenance.py') != MANIFEST['added']['atlas_base_maintenance.py']['sha256']:
        raise Fail('maintenance module missing or different')
    names = MANIFEST['stage_b_files']
    files = selected(candidate_files(env, 'B'), names)
    compile_staged(env, files)
    base0 = require_running(env, env.base)
    rec0 = require_running(env, env.recovery)
    if 'ATLAS base maintenance coordination: loaded' not in env.journal(rec0.get('InvocationID')):
        raise Fail('running recovery invocation has not reported coordination loaded')
    prot0 = identities(env, env.protected)
    require_safe(env, ev, 'B-pre')
    resources_strict(env, ev, 'B-pre', env.preflight_s)
    bm, m = maint(env)
    session = arm_or_fail(bm, m, 'stage 28 RC bridge deployment', env.lease_s, env.in_flight_wait_s)
    ev.log(f'lease armed session {session}')
    state = {'files': False, 'restarted': False}
    meta = None
    try:
        dropin_install(env)
        ev.log('runtime ExecCondition gate loaded')
        wait_ack(env, ev, m, session, int(rec0['MainPID']))
        if unit_state(env, env.base).get('MainPID') != base0['MainPID']:
            raise Fail('base changed while entering maintenance')
        meta = backup(env, ev, names)
        for n in names:                              # helpers first, base driver last
            mode = meta[n]['mode'] if meta[n]['present'] else 0o644
            install_atomic(files[n], env.scripts / n, mode)
        state['files'] = True
        ev.log('files installed: ' + ', '.join(f'{n}={sha(env.scripts / n)[:12]}' for n in names))
        require_safe(env, ev, 'B-pre-restart', count=2)
        resources_strict(env, ev, 'B-pre-restart', env.pre_restart_s)
        m.authorize_start(session)
        with CpuRecorder(env) as cpu, SafetyRecorder(env, required=NON_BASE_PREDICATES) as safe:
            env.sleep(2.5)
            t0 = time.time()
            ev.log('restarting rover-base-telemetry ONLY (1 authorised start)')
            state['restarted'] = True
            r = env.systemctl('restart', env.base, timeout=90, check=False)
            ev.save('restart', {'rc': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr})
            try:
                verify_base_back(env, ev, m, session, t0, base0, expect_used=1)
                rc = verify_rc(env, ev)
                resources_after_restart(env, ev, 'B-post', args.cpu_rule, cpu, t0, args.transient_bound_s, safe)
            finally:
                ev.save('cpu-recorder-B', {'t_restart': t0, 'samples': cpu.samples, 'ram_temp': cpu.rt})
                ev.save('safety-recorder-B', {'t_restart': t0, 'snapshots': safe.snaps})
        require_safe(env, ev, 'B-post')
        if identities(env, env.protected) != prot0:
            raise Fail('a protected service identity changed')
        if unit_state(env, env.recovery).get('MainPID') != rec0['MainPID']:
            raise Fail('recovery restarted during the window')
        bad = recovery_base_restarts(env, rec0['InvocationID'], t0)
        if bad:
            raise Fail(f'recovery issued a base restart during the window: {bad}')
        release(env, ev, m, session)
    except Exception as exc:
        ev.log(f'DEPLOY FAILED: {exc!r}')
        ev.save('failure', {'error': repr(exc), 'state': state})
        result = rollback_bridge(env, ev, m, session, meta, state, base0)
        ev.save('result', {'result': result, 'error': repr(exc)})
        ev.seal()
        return 1
    ev.save('result', {'result': 'PASS', 'rc': rc, 'base_pid_before': base0['MainPID'],
                       'base_pid_after': unit_state(env, env.base).get('MainPID'),
                       'hashes': {n: sha(env.scripts / n) for n in names}})
    ev.log('DEPLOY PASS')
    ev.seal()
    return 0


def verify_base_back(env, ev, m, session, t0, base0, expect_used):
    deadline = time.monotonic() + env.ready_timeout_s
    while True:
        s = unit_state(env, env.base)
        new = s.get('InvocationID') and s.get('InvocationID') != base0.get('InvocationID')
        log = env.journal(s.get('InvocationID')) if new else ''
        if new and s.get('ActiveState') == 'active' and s.get('SubState') == 'running' and re.search(env.ready_re, log):
            break
        if s.get('ActiveState') in ('failed', 'inactive') or time.monotonic() > deadline:
            raise Fail(f'base did not come back: {s.get("ActiveState")}/{s.get("SubState")}')
        env.sleep(1)
    if s['MainPID'] == base0['MainPID']:
        raise Fail('base MainPID unchanged: restart did not happen')
    lease = m.evaluate().lease or {}
    if lease.get('used') != expect_used or lease.get('tokens') != expect_used:
        raise Fail(f'gate consumption mismatch (used={lease.get("used")} tokens={lease.get("tokens")}): '
                   'a start was not the authorised one')
    for pat in ('Traceback', 'can DRIVE from SBUS'):
        if pat in log:
            raise Fail(f'base log contains {pat!r}')
    # READY precedes the first telemetry by up to a DDS rediscovery gap: wait (bounded) for live data, then judge.
    deadline = time.monotonic() + env.telemetry_timeout_s
    while True:
        snap = safety_snapshot(env)
        if snap['predicates'].get('telemetry_live') and snap['predicates'].get('encoders_fresh'):
            break
        if time.monotonic() > deadline:
            ev.save('telemetry-timeout', snap)
            raise Fail(f'telemetry did not resume within {env.telemetry_timeout_s} s after READY')
        env.sleep(0.5)
    s2 = require_running(env, env.base)
    if s2['MainPID'] != s['MainPID']:
        raise Fail('base restarted again after coming back')
    require_safe(env, ev, 'B-telemetry', count=3, spacing=2.0)
    ev.log(f'base back: pid {s["MainPID"]}, board ready, authorised starts used {expect_used}')
    return s


def verify_rc(env, ev):
    deadline = time.monotonic() + env.rc_publisher_timeout_s
    st = {}
    while time.monotonic() < deadline:
        st = env.get('/api/flysky/state')
        if int(st.get('publishers') or 0) >= 1:
            break
        env.sleep(1)
    ev.save('flysky-state', st)
    if int(st.get('publishers') or 0) < 1:
        raise Fail('/atlas/rc/frames publisher not visible to the Test Lab')
    link = st.get('link', {})
    ev.log(f'/atlas/rc/frames publishers={st.get("publishers")} link={link.get("state")} frames={link.get("frames_total")}')
    return {'publishers': st.get('publishers'), 'link': link}


def release(env, ev, m, session):
    m.release(session)                  # gate + recovery now treat the lease as NONE
    dropin_remove(env)
    m.clear(session)
    ev.log('maintenance released: drop-in removed, lease cleared')


def rollback_bridge(env, ev, m, session, meta, state, base0):
    try:
        if state['files'] and meta:
            restore(env, ev, meta)
        if state['restarted'] or (state['files'] and unit_state(env, env.base).get('MainPID') != base0['MainPID']):
            m.revoke_unused(session)
            before_rb = wait_quiescent(env, env.base)
            m.authorize_start(session)
            with CpuRecorder(env) as cpu:
                env.sleep(1.5)
                t = time.time()
                ev.log('rollback: ONE authorised base restart with the original files')
                env.systemctl('restart', env.base, timeout=90, check=False)
                lease = m.evaluate().lease or {}
                verify_base_back(env, ev, m, session, t, before_rb, expect_used=lease.get('tokens'))
                record_rollback_cpu(env, ev, 'B', cpu, t)
        release(env, ev, m, session)
        ev.log('ROLLED_BACK: originals restored and verified; maintenance released')
        return 'ROLLED_BACK'
    except Exception as exc:
        ev.log(f'ROLLBACK INCOMPLETE: {exc!r}. Fail-closed hold retained (no automatic restart). '
               f'Owner action: inspect, then `deploy_rc_bridge.py abandon` (see rollback plan).')
        return 'ROLLBACK_INCOMPLETE_OWNER_ACTION'


def abandon(env, args):
    """Operator-only: remove the runtime drop-in and any lease after manual inspection. Starts nothing."""
    bm, m = maint(env)
    v = m.evaluate()
    print(json.dumps({'before': v.state, 'reason': v.reason, 'lease': v.lease}))
    dropin_remove(env)
    m.clear(force=True)
    print('maintenance state removed; base service NOT started. Start it yourself only after inspection.')
    return 0


def preflight(env, args):
    ev = Evidence(env, 'preflight')
    ok = True
    rec = sha(env.scripts / 'atlas_sensor_recovery.py')
    stage_a = rec == MANIFEST['modified']['atlas_sensor_recovery.py']['candidate_sha256']
    ev.log('stage A (recovery coordination): ' + ('INSTALLED' if stage_a else 'not installed'))
    for st in (('B',) if stage_a else ('A', 'B')):
        try:
            candidate_files(env, st)
            ev.log(f'package stage {st}: candidates rebuilt from live baselines, all hashes match')
        except Exception as exc:
            ok = False
            ev.log(f'package stage {st}: {exc}')
    for label, fn in (('safety', lambda: require_safe(env, ev, 'preflight')),
                      ('resources', lambda: resources_strict(env, ev, 'preflight', env.preflight_s)),
                      ('base', lambda: require_running(env, env.base)),
                      ('recovery', lambda: require_running(env, env.recovery))):
        try:
            fn()
        except Exception as exc:
            ok = False
            ev.log(f'{label}: {exc}')
    ev.save('result', {'result': 'GO' if ok else 'NO-GO'})
    ev.seal()
    return 0 if ok else 1


def main(argv=None, env=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('action', choices=['preflight', 'install-recovery', 'deploy', 'abandon'])
    p.add_argument('--cpu-rule', choices=['strict', 'transient'])
    p.add_argument('--transient-bound-s', type=float,
                   help='transient rule only: seconds after the restart in which >75 %% CPU samples are tolerated '
                        '(reported, never hidden); no default; max %d' % MAX_TRANSIENT_BOUND_S)
    p.add_argument('--owner-confirms-transmitter-off', action='store_true')
    p.add_argument('--owner-confirms-actuators-disconnected', action='store_true')
    p.add_argument('--evidence-root', help='evidence directory root (default ~/project-atlas-migration)')
    a = p.parse_args(argv)
    env = env or Env()
    if a.evidence_root:
        env.evidence_root = Path(a.evidence_root)
    if a.action != 'preflight':
        if os.environ.get('OWNER_APPROVED') != 'yes':
            print('refused: OWNER_APPROVED=yes required (separate owner approval)')
            return 2
        if a.action in ('install-recovery', 'deploy') and not (a.cpu_rule and a.owner_confirms_actuators_disconnected
                                                              and a.owner_confirms_transmitter_off):
            print('refused: --cpu-rule and both owner confirmations are required')
            return 2
        if (a.cpu_rule == 'transient') != (a.transient_bound_s is not None) or (
                a.transient_bound_s is not None and not 0 < a.transient_bound_s <= MAX_TRANSIENT_BOUND_S):
            print(f'refused: --cpu-rule transient needs --transient-bound-s in (0, {MAX_TRANSIENT_BOUND_S:.0f}]; '
                  'strict takes no bound')
            return 2
    ev = None
    try:
        if a.action in ('install-recovery', 'deploy'):
            ev = Evidence(env, 'recovery-coordination' if a.action == 'install-recovery' else 'rc-bridge')
            return {'install-recovery': install_recovery, 'deploy': deploy}[a.action](env, a, ev)
        return {'preflight': preflight, 'abandon': abandon}[a.action](env, a)
    except Fail as exc:
        print(f'REFUSED (no change made): {exc}')
        if ev is not None:
            ev.log(f'REFUSED (no change made): {exc}')
            ev.save('result', {'result': 'REFUSED_NO_CHANGE', 'error': repr(exc)})
            ev.seal()
        return 3
    except Exception as exc:          # never leave an unexplained traceback as the only evidence
        print(f'ERROR (inspect evidence; maintenance state shown by `atlas_base_maintenance.py status`): {exc!r}')
        return 4


if __name__ == '__main__':
    raise SystemExit(main())
