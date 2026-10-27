#!/usr/bin/env python3
"""SIMULATION ONLY: end-to-end tests of Stage 28 base-maintenance coordination on a REAL systemd user manager.

Run as an unprivileged user that has its own `systemd --user` (XDG_RUNTIME_DIR set). Nothing here touches ROS,
serial ports, the Jetson or production paths. Units are fakes; atlas_sensor_recovery.py is the REAL file
(original baseline or the Stage 28 candidate) under a stub rclpy; the deployer is the real deploy_rc_bridge.py.

usage: run_sim.py <workdir> [scenario ...]
"""
import http.server
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import traceback

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
UID = os.getuid()
RUN = Path(f'/run/user/{UID}')
UNITS = Path.home() / '.config/systemd/user'
BASE = 'rover-base-telemetry.service'
REC = 'atlas-sensor-recovery.service'
SENSORS = ['atlas-lidar.service', 'atlas-camera.service', 'rover-radar.service', 'rover-daly-bms.service',
           'atlas-uno-r4-sensor-hub.service', 'atlas-ekf.service', 'rover-cellular.service', 'atlas-slam-fast.service']
PROTECTED = ['atlas-cmd-vel-mux.service', 'rover-status-web.service']
W = None            # workdir
FOX_PORT = None     # fake foxglove_bridge (independent safety observer source)
STATE = None        # sim state dir
SCRIPTS = None      # sim "production" scripts dir


def free_port():
    import socket
    k = socket.socket()
    k.bind(('127.0.0.1', 0))
    port = k.getsockname()[1]
    k.close()
    return port


def sh(*a, check=True, timeout=60):
    return subprocess.run(['systemctl', '--user', *a], capture_output=True, text=True, check=check, timeout=timeout)


def show(unit, *props):
    out = sh('show', unit, *sum((['-p', p] for p in props), [])).stdout
    return dict(line.split('=', 1) for line in out.splitlines() if '=' in line)


# ------------------------------------------------------------------ sim world
def world(**kw):
    p = STATE / 'world.json'
    d = json.loads(p.read_text()) if p.exists() else {}
    d.update(kw)
    p.write_text(json.dumps(d))
    fox = {k: d[k] for k in ('stop_latched', 'cmd_lin', 'cmd_ang', 'encoder_state', 'source') if k in d}
    tmp = STATE / 'fox_ctl.tmp'
    tmp.write_text(json.dumps(fox))
    os.replace(tmp, STATE / 'fox_ctl.json')


def flag(name, on=True, value=None):
    p = STATE / name
    if on:
        p.write_text('' if value is None else str(value))
    elif p.exists():
        p.unlink()


def hb():
    try:
        return json.loads((STATE / 'hb').read_text())
    except (OSError, ValueError):
        return None


def starts():
    p = STATE / 'starts.log'
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def log_lines(inv=None):
    p = W / 'logs' / 'all.log'
    rows = []
    for line in (p.read_text(errors='replace').splitlines() if p.exists() else []):
        parts = line.split(' ', 2)
        if len(parts) == 3 and (inv is None or parts[0] == inv):
            try:
                rows.append((parts[0], float(parts[1]), parts[2]))
            except ValueError:
                pass
    return rows


def recovery_lines(since=0.0):
    inv = show(REC, 'InvocationID')['InvocationID']
    return [m for _, t, m in log_lines(inv) if t >= since]


# ------------------------------------------------------------------ fake status web
class Web(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        w = json.loads((STATE / 'world.json').read_text())
        h = hb()
        age = time.time() - h['wall'] if h else 999.0
        if self.path == '/api/estop/state':
            body = {'latched': w.get('estop', True)}
        elif self.path == '/api/status':
            fresh = age <= 1.0
            body = {'ros': {
                'control_policy': {'age': 0.1, 'value': json.dumps({
                    'manual_only': True, 'commission_armed': False, 'stop_latched': w.get('stop_latched', True),
                    'source': w.get('source', 'STOPPED')})},
                'cmd_vel': {'age': 0.1, 'value': {'lin': w.get('cmd_lin', 0.0), 'ang': w.get('cmd_ang', 0.0)}},
                'motor_speed': {'age': age, 'value': w.get('motor_speed', 0.0)},
                'web_drive': {'age': 0.1, 'value': 'STOP'},
                'drive_pid': {'age': 0.1, 'value': json.dumps({'active': False, 'state': 'DISABLED'})},
                'odom': {'age': 0.1, 'value': {'x': 0.0, 'y': 0.0, 'vx': 0.0, 'wz': 0.0}},
                **{f'enc_m{i}': {'age': age, 'value': v + (w.get('enc_drift', 0) if i == 1 else 0)}
                   for i, v in zip(range(1, 5), (-13, 27, -40, 16))},
                'encoder_health': {'age': age, 'value': json.dumps({
                    'state': w.get('encoder_state', 'READY'), 'packet_fresh': fresh, 'packet_age_s': round(age, 3),
                    'serial_encoder_packets': (h or {}).get('n', 0)})},
            }}
        elif self.path == '/api/flysky/state':
            pub = 0
            try:
                if h and age <= 1.0 and int((STATE / 'rc_publisher').read_text()) == h['pid']:
                    pub = 1
            except (OSError, ValueError):
                pass
            body = {'publishers': pub, 'link': {'state': 'NO_SOURCE' if not pub else 'WAITING_FOR_FRAMES',
                                                'frames_total': 0}}
        else:
            self.send_response(404)
            self.end_headers()
            return
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


# ------------------------------------------------------------------ deployer env
def load_deployer():
    spec = importlib.util.spec_from_file_location('deploy_rc_bridge', PKG / 'deploy_rc_bridge.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


D = load_deployer()
sys.path.insert(0, str(PKG))


class SimEnv(D.Env):
    """Real systemctl against the sim user manager; scripted CPU; sim journal."""

    def __init__(self, port, cpu=None, **kw):
        super().__init__(scripts=SCRIPTS, api=f'http://127.0.0.1:{port}', evidence_root=W / 'evidence',
                         protected=PROTECTED, python=sys.executable, preflight_s=5, pre_restart_s=3, steady_s=5,
                         ack_timeout_s=8, in_flight_wait_s=30, ready_timeout_s=30,
                         rc_publisher_timeout_s=10, recovery_ready_timeout_s=30, lease_s=240, **kw)
        self.cpu = cpu or {}
        self.transient_left = 0
        self.calls = []

    def systemctl(self, *args, timeout=30, check=True):
        self.calls.append((time.time(), args))
        if args and args[0] == 'restart':
            self.transient_left = self.cpu.get('transient_n', 3)
        return super().systemctl(*args, timeout=timeout, check=check)

    def make_observer(self, base_pid):
        import atlas_safety_observer as so
        return so.SafetyObserver(port=FOX_PORT, base_pid=base_pid, odom_path=STATE / 'odom.json')

    def journal(self, invocation, since_epoch=0.0):
        return '\n'.join(m for _, t, m in log_lines(invocation) if t >= since_epoch)

    def cpu_samples(self, n):
        out = []
        for _ in range(n):
            if self.transient_left > 0:
                self.transient_left -= 1
                out.append(self.cpu.get('transient_val', 98.8))
            else:
                out.append(self.cpu.get('steady', 66.0))
        return out

    def ram_temp(self):
        return 60.0, {'cpu-thermal': 64.7, 'tj-thermal': 64.7}


# ------------------------------------------------------------------ setup
def unit(name, exec_, extra=''):
    (UNITS / name).write_text(f'''[Unit]
Description=SIM {name}
[Service]
Environment=SIM_STATE={STATE} SIM_SCRIPTS={SCRIPTS} PYTHONUNBUFFERED=1
ExecStart={exec_}
StandardOutput=append:{W}/logs/all.log
StandardError=append:{W}/logs/all.log
{extra}
''')


def put(src, dst):
    """Copy with production-like modes (yahboom_base.py 0755, others 0644)."""
    dst = Path(dst)
    if dst.exists():
        dst.unlink()
    shutil.copyfile(src, dst)
    os.chmod(dst, 0o755 if dst.name == 'yahboom_base.py' else 0o644)


def setup(workdir):
    global W, STATE, SCRIPTS
    W = Path(workdir)
    if W.exists():
        shutil.rmtree(W)
    STATE, SCRIPTS = W / 'state', W / 'scripts'
    for d in (STATE, SCRIPTS, W / 'logs', W / 'evidence'):
        d.mkdir(parents=True)
    if os.environ.get('SIM_BASELINES'):
        for p in Path(os.environ['SIM_BASELINES']).iterdir():
            put(p, SCRIPTS / p.name)
    else:
        subprocess.run([str(HERE / 'fetch_baselines.sh'), str(SCRIPTS)], check=True, capture_output=True)
    UNITS.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    unit(BASE, f'{py} {HERE}/fake_base.py', 'Type=notify\nRestart=on-failure\nRestartSec=3\nWatchdogSec=5\n'
         'TimeoutStopSec=5\nKillMode=control-group\nSendSIGKILL=yes\nNotifyAccess=main')
    unit(REC, f'{py} {HERE}/sim_recovery_main.py',
         'Type=simple\nRestart=always\nRestartSec=3\nEnvironment=ATLAS_GNSS_ENABLED=0 SIM_GRACE=4')
    for s in SENSORS + PROTECTED:
        hbv = f'Environment=SIM_HB={STATE}/lidar_hb SIM_NAME={s}' if s == 'atlas-lidar.service' else f'Environment=SIM_NAME={s}'
        unit(s, f'{py} {HERE}/sleeper.py', 'Type=simple\n' + hbv)
    world(estop=True, stop_latched=True, cmd_lin=0.0, cmd_ang=0.0, encoder_state='READY', recovery_encoder_state=None)
    global FOX_PORT
    FOX_PORT = free_port()
    subprocess.Popen([sys.executable, str(HERE / 'fake_foxglove.py'), str(FOX_PORT), str(STATE / 'fox_ctl.json')])
    reset_runtime()
    sh('daemon-reload')
    for s in SENSORS + PROTECTED + [BASE, REC]:
        sh('restart', s, timeout=60)
    time.sleep(6)            # recovery startup grace (sim: 4 s)


def reset_runtime():
    shutil.rmtree(RUN / 'atlas-base-maintenance', ignore_errors=True)
    shutil.rmtree(RUN / 'systemd/user' / f'{BASE}.d', ignore_errors=True)


def install_original_recovery():
    put(SCRIPTS.parent / 'baselines' / 'atlas_sensor_recovery.py', SCRIPTS / 'atlas_sensor_recovery.py')
    p = SCRIPTS / 'atlas_base_maintenance.py'
    if p.exists():
        p.unlink()


def fresh_recovery():
    """Restart recovery (fresh attempt budget) and wait past its grace."""
    sh('restart', REC)
    time.sleep(6)


def wait_for(pred, timeout, step=0.2):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(step)
    return False


# ------------------------------------------------------------------ scenarios
RESULTS = []


def scenario(fn):
    def run(port):
        name = fn.__name__
        t0 = time.time()
        print(f'\n=== {name}', flush=True)
        try:
            detail = fn(port) or {}
            ok = detail.pop('_ok', True)
        except AssertionError as exc:
            ok, detail = False, {'assert': str(exc), 'tb': traceback.format_exc()[-1500:]}
        except Exception as exc:
            ok, detail = False, {'error': repr(exc), 'tb': traceback.format_exc()[-2500:]}
        RESULTS.append({'scenario': name, 'pass': ok, 'seconds': round(time.time() - t0, 1), **detail})
        print(f'--- {name}: {"PASS" if ok else "FAIL"} {json.dumps(detail)[:600]}', flush=True)
    run.__name__ = fn.__name__
    return run


def base_restart_by_recovery(lines):
    return [m for m in lines if 'RECOVERING:' in m and BASE in m]


@scenario
def s00_original_recovery_races_manual_restart(port):
    """Baseline evidence: with the ORIGINAL recovery, a manual base restart with a realistic DDS gap triggers a
    competing recovery restart (the blocker). Proves the race is real in this model."""
    install_original_recovery()
    reset_runtime()
    fresh_recovery()
    flag('init_s', value=3)
    flag('stop_s', value=3)          # slow shutdown: "deactivating" is not seen as a systemd restart
    n0 = len(starts())
    t0 = time.time()
    sh('restart', BASE, timeout=60)
    wait_for(lambda: len(base_restart_by_recovery(recovery_lines(t0))) > 0, 25)
    time.sleep(8)
    lines = recovery_lines(t0)
    comp = base_restart_by_recovery(lines)
    flag('stop_s', on=False)
    # Observation, not a gate: whether the 2-s check lands inside the stop phase is timing-dependent
    # (reproduced in 2 of 3 full runs on 2026-10-27). The coordinated path is gated by s03.
    return {'competing_restart_reproduced': bool(comp), 'manual_starts': len(starts()) - n0,
            'recovery_lines': (comp or [m for m in lines if 'DEFERRED' in m])[:2]}


@scenario
def s00b_original_recovery_defers_during_long_init(port):
    """Informative: with a fast stop and a 10 s init, the original recovery defers to systemd and then its single
    encoder_health attempt (1 per 600 s) is spent, so it does not compete in this timing."""
    install_original_recovery()
    reset_runtime()
    fresh_recovery()
    flag('init_s', value=10)
    n0 = len(starts())
    t0 = time.time()
    sh('restart', BASE, timeout=60)
    time.sleep(10)
    lines = recovery_lines(t0)
    flag('init_s', on=False)
    return {'base_starts': len(starts()) - n0, 'competing_restart': bool(base_restart_by_recovery(lines)),
            'deferred': [m for m in lines if 'DEFERRED' in m][:1]}


@scenario
def s01_stage_a_install_recovery(port):
    install_original_recovery()
    reset_runtime()
    fresh_recovery()
    env = SimEnv(port, cpu={'transient_n': 2, 'transient_val': 98.8, 'steady': 66.0})
    base_pid = show(BASE, 'MainPID')['MainPID']
    os.environ['OWNER_APPROVED'] = 'yes'
    rc = D.main(['install-recovery', '--cpu-rule', 'transient', '--transient-bound-s', '10', '--owner-confirms-transmitter-off',
                 '--owner-confirms-actuators-disconnected'], env=env)
    assert rc == 0, f'stage A rc={rc}'
    assert D.sha(SCRIPTS / 'atlas_sensor_recovery.py') == D.MANIFEST['modified']['atlas_sensor_recovery.py']['candidate_sha256']
    assert show(BASE, 'MainPID')['MainPID'] == base_pid, 'base must not be restarted by stage A'
    assert any('coordination: loaded' in m for m in recovery_lines()), 'patched recovery not loaded'
    restarts = [c for _, c in env.calls if c[0] == 'restart']
    assert restarts == [('restart', REC)], restarts
    return {'systemctl_restarts': restarts, 'base_pid_unchanged': base_pid}


@scenario
def s02_stage_a_strict_rule_rolls_back(port):
    """Strict single-sample rule + realistic 98.8 % restart transient -> stage A fails and restores the original."""
    install_original_recovery()
    reset_runtime()
    fresh_recovery()
    env = SimEnv(port, cpu={'transient_n': 2, 'transient_val': 98.8, 'steady': 66.0})
    rc = D.main(['install-recovery', '--cpu-rule', 'strict', '--owner-confirms-transmitter-off',
                 '--owner-confirms-actuators-disconnected'], env=env)
    assert rc == 1, rc
    assert D.sha(SCRIPTS / 'atlas_sensor_recovery.py') == D.MANIFEST['modified']['atlas_sensor_recovery.py']['baseline_sha256']
    assert not (SCRIPTS / 'atlas_base_maintenance.py').exists()
    assert show(REC, 'ActiveState')['ActiveState'] == 'active'
    return {'restored': 'original recovery c6b5ac79', 'rule': 'strict fails on 98.8 % transient'}


def ensure_stage_a(port):
    if D.sha(SCRIPTS / 'atlas_sensor_recovery.py') != D.MANIFEST['modified']['atlas_sensor_recovery.py']['candidate_sha256']:
        install_original_recovery()
        env = SimEnv(port, cpu={'transient_n': 1})
        assert D.main(['install-recovery', '--cpu-rule', 'transient', '--transient-bound-s', '10', '--owner-confirms-transmitter-off',
                       '--owner-confirms-actuators-disconnected'], env=env) == 0


def ensure_base_running():
    for f in ('crash', 'fail_init', 'candidate_crash_after_s', 'candidate_fails_init', 'hang'):
        flag(f, on=False)
    st = starts()
    if show(BASE, 'ActiveState')['ActiveState'] != 'active' or (st and st[-1]['rc']):
        sh('restart', BASE, timeout=60)          # every scenario starts with the ORIGINAL base code running
        time.sleep(1)
    assert show(BASE, 'ActiveState')['ActiveState'] == 'active'


def restore_stage_b_baseline():
    for n in ('yahboom_base.py', 'Rosmaster_Lib.py'):
        put(SCRIPTS.parent / 'baselines' / n, SCRIPTS / n)
    for n in ('atlas_yahboom_rc_report.py', 'atlas_rc_readonly_bridge.py'):
        if (SCRIPTS / n).exists():
            (SCRIPTS / n).unlink()
    for f in ('candidate_fails_init', 'candidate_crash_after_s', 'crash', 'fail_init', 'gap_s', 'init_s', 'stop_s',
              'rc_publisher'):
        flag(f, on=False)
    reset_runtime()
    ensure_base_running()


def deploy(port, **cpu):
    env = SimEnv(port, cpu={'transient_n': 3, 'transient_val': 98.8, 'steady': 66.0, **cpu})
    rc = D.main(['deploy', '--cpu-rule', 'transient', '--transient-bound-s', '10', '--owner-confirms-transmitter-off',
                 '--owner-confirms-actuators-disconnected'], env=env)
    return rc, env


def last_result():
    ev = sorted((W / 'evidence').glob('stage28-rc-bridge-*'))[-1]
    return json.loads(sorted(ev.glob('*-result.json'))[-1].read_text()), ev


def clean_runtime_ok():
    dropin = RUN / 'systemd/user' / f'{BASE}.d' / '90-atlas-base-maintenance.conf'
    lease = RUN / 'atlas-base-maintenance' / 'lease.json'
    loaded = '90-atlas-base-maintenance' in show(BASE, 'DropInPaths')['DropInPaths']
    return not dropin.exists() and not lease.exists() and not loaded


@scenario
def s03_stage_b_deploy_happy_path_with_dds_gap(port):
    ensure_stage_a(port)
    restore_stage_b_baseline()
    reset_runtime()
    fresh_recovery()
    flag('init_s', value=3)
    flag('gap_s', value=4)          # the same gap that made the original recovery race in s00
    prot0 = {u: show(u, 'MainPID')['MainPID'] for u in PROTECTED + SENSORS}
    rec_pid = show(REC, 'MainPID')['MainPID']
    n0 = len(starts())
    t0 = time.time()
    rc, env = deploy(port)
    res, ev = last_result()
    new = starts()[n0:]
    assert rc == 0 and res['result'] == 'PASS', res
    assert len(new) == 1 and new[0]['rc'] is True, f'exactly one base start expected: {new}'
    assert not base_restart_by_recovery(recovery_lines(t0)), 'recovery competed'
    assert any('RECOVERY HELD' in m or 'HOLD ACTIVE' in m for m in recovery_lines(t0)), 'recovery never held'
    assert show(REC, 'MainPID')['MainPID'] == rec_pid
    assert {u: show(u, 'MainPID')['MainPID'] for u in PROTECTED + SENSORS} == prot0
    assert clean_runtime_ok(), 'drop-in/lease left behind'
    for n in D.MANIFEST['stage_b_files']:
        want = D.MANIFEST['modified'].get(n, {}).get('candidate_sha256') or D.MANIFEST['added'][n]['sha256']
        assert D.sha(SCRIPTS / n) == want, n
    assert D.sha(SCRIPTS / 'atlas_flysky_core.py') == D.MANIFEST['must_remain']['atlas_flysky_core.py']
    held = [m for m in recovery_lines(t0) if 'HELD' in m or 'HOLD' in m or 'CANCELED' in m]
    return {'base_starts': len(new), 'evidence': str(ev), 'recovery_hold_lines': held[:3],
            'systemctl_calls': [c for _, c in env.calls if c[0] in ('restart', 'daemon-reload')]}


@scenario
def s04_inflight_recovery_restart_blocks_entry(port):
    """Recovery is itself restarting the base (slow init) when the deployer starts: the deployer must not
    restart the base until recovery's restart is over (arm refused, or ack in_flight waits)."""
    ensure_stage_a(port)
    restore_stage_b_baseline()
    reset_runtime()
    fresh_recovery()
    flag('init_s', value=4)            # production init must stay < WatchdogSec=5 (watchdog is armed at start)
    world(encoder_state='CRITICAL')                # makes recovery schedule a base restart
    assert wait_for(lambda: any('RECOVERING: encoder_health' in m for m in recovery_lines(time.time() - 30)), 20), \
        'recovery did not start its base restart'
    world(encoder_state='READY')
    t_dep = time.time()
    rc, env = deploy(port)
    lines = recovery_lines(t_dep - 30)
    st = starts()
    # no two base processes may have started within one init period of each other (no overlap)
    times = [s['t'] for s in st[-4:]]
    overlap = any(b - a < 4 for a, b in zip(times, times[1:]))
    out = {'deploy_rc': rc, 'start_times': times, 'recovery_lines': [m for m in lines if 'RECOVER' in m][:4]}
    try:
        res, _ = last_result()
        out['result'] = res.get('result')
    except Exception:
        out['result'] = 'REFUSED before evidence result'
    assert not overlap, f'overlapping base starts: {times}'
    flag('init_s', on=False)
    return out


@scenario
def s04b_deployer_waits_for_recovery_confirm_loop(port):
    """Recovery restarted the base and is still in its confirm loop (base already active): the deployer arms,
    sees ack in_flight=True and must not restart the base until recovery's own attempt has finished."""
    ensure_stage_a(port)
    restore_stage_b_baseline()
    fresh_recovery()
    flag('init_s', value=2)
    t0 = time.time()
    world(recovery_encoder_state='CRITICAL')       # only recovery sees the fault
    assert wait_for(lambda: any('RECOVERING: encoder_health' in m for m in recovery_lines(t0)), 20)
    assert wait_for(lambda: show(BASE, 'ActiveState')['ActiveState'] == 'active', 15)
    release_at = time.time() + 12
    threading.Thread(target=lambda: (time.sleep(max(0, release_at - time.time())),
                                     world(recovery_encoder_state=None)), daemon=True).start()
    n0 = len(starts())
    rc, env = deploy(port)
    res, ev = last_result()
    new = starts()[n0:]
    ack = json.loads(next(ev.glob('*-ack.json')).read_text())
    recovered = [(t, m) for _, t, m in log_lines(show(REC, 'InvocationID')['InvocationID'])
                 if t >= t0 and ('RECOVERED' in m or 'RECOVERY INCOMPLETE' in m)]
    assert rc == 0 and res['result'] == 'PASS', res
    assert len(new) == 1 and recovered and new[0]['t'] > recovered[0][0], \
        f'deployer restarted before recovery finished: start {new} recovered {recovered}'
    return {'recovery_finished': recovered[0][1][:90], 'deploy_start_after_s': round(new[0]['t'] - recovered[0][0], 1),
            'ack': ack}


@scenario
def s05_candidate_crash_rolls_back_without_loop(port):
    """New base code crashes 1 s after READY: systemd's auto-restart is withheld by the gate (no loop), the
    deployer restores the originals and performs exactly one authorised rollback start."""
    ensure_stage_a(port)
    restore_stage_b_baseline()
    reset_runtime()
    fresh_recovery()
    flag('candidate_crash_after_s', value=1)
    n0 = len(starts())
    rc, env = deploy(port)
    res, ev = last_result()
    new = starts()[n0:]
    flag('candidate_crash_after_s', on=False)
    assert rc == 1 and res['result'] == 'ROLLED_BACK', res
    assert [s['rc'] for s in new] == [True, False], f'expected candidate start then rollback start only: {new}'
    assert D.sha(SCRIPTS / 'yahboom_base.py') == D.MANIFEST['modified']['yahboom_base.py']['baseline_sha256']
    assert not (SCRIPTS / 'atlas_yahboom_rc_report.py').exists()
    assert show(BASE, 'ActiveState')['ActiveState'] == 'active'
    assert clean_runtime_ok()
    return {'starts': new, 'error': res.get('error')}


@scenario
def s06_cpu_never_settles_rolls_back(port):
    ensure_stage_a(port)
    restore_stage_b_baseline()
    reset_runtime()
    fresh_recovery()
    n0 = len(starts())
    rc, env = deploy(port, transient_n=999)
    res, _ = last_result()
    new = starts()[n0:]
    assert rc == 1 and res['result'] == 'ROLLED_BACK', res
    assert [s['rc'] for s in new] == [True, False], new
    assert clean_runtime_ok()
    return {'error': res.get('error'), 'starts': len(new)}


@scenario
def s07_stop_guard_broken_before_restart(port):
    """E-STOP released (stop_latched False) right before the restart: no base restart, files restored."""
    ensure_stage_a(port)
    restore_stage_b_baseline()
    reset_runtime()
    fresh_recovery()
    n0 = len(starts())
    env = SimEnv(port, cpu={'transient_n': 0})
    orig = D.require_safe

    def trip(env_, ev, label, **kw):
        if label == 'B-pre-restart':
            world(stop_latched=False)
        return orig(env_, ev, label, **kw)
    D.require_safe = trip
    try:
        rc = D.main(['deploy', '--cpu-rule', 'transient', '--transient-bound-s', '10', '--owner-confirms-transmitter-off',
                     '--owner-confirms-actuators-disconnected'], env=env)
    finally:
        D.require_safe = orig
        world(stop_latched=True)
    res, _ = last_result()
    assert rc == 1 and res['result'] == 'ROLLED_BACK', res
    assert len(starts()) == n0, 'base must not have been restarted'
    assert D.sha(SCRIPTS / 'yahboom_base.py') == D.MANIFEST['modified']['yahboom_base.py']['baseline_sha256']
    assert clean_runtime_ok()
    return {'error': res.get('error')}


def arm_with_owner(seconds=60):
    owner = subprocess.Popen(['sleep', '600'])
    sys.path.insert(0, str(SCRIPTS))
    import atlas_base_maintenance as bm
    m = bm.Maintenance()
    s = m.arm('sim owner', seconds, owner_pid=owner.pid)
    return owner, m, s


@scenario
def s08_owner_crash_fails_closed_then_abandon(port):
    ensure_stage_a(port)
    restore_stage_b_baseline()
    reset_runtime()
    fresh_recovery()
    owner, m, s = arm_with_owner()
    env = SimEnv(port)
    D.dropin_install(env)                 # the deployer had installed its gate, then died
    owner.kill()
    owner.wait()
    t0 = time.time()
    assert m.evaluate().state == 'INVALID'
    flag('crash')                         # base dies; systemd would auto-restart; recovery would want to restart
    time.sleep(10)
    flag('crash', on=False)
    lines = recovery_lines(t0)
    st = show(BASE, 'ActiveState', 'SubState')
    assert st['ActiveState'] == 'inactive', f'gate must withhold auto-restart with an orphaned lease: {st}'
    assert not base_restart_by_recovery(lines), 'recovery must not restart the base under an INVALID lease'
    assert any('HOLD INVALID' in x for x in lines), 'INVALID must be reported'
    rc = D.main(['abandon'], env=env)
    assert rc == 0 and clean_runtime_ok()
    sh('start', BASE, timeout=60)        # owner's manual start after inspection
    assert show(BASE, 'ActiveState')['ActiveState'] == 'active'
    return {'held_lines': [x for x in lines if 'BASE' in x or 'HELD' in x][:3]}


@scenario
def s09_expired_lease_stays_closed(port):
    ensure_stage_a(port)
    reset_runtime()
    owner, m, s = arm_with_owner(2)
    time.sleep(3)
    v = m.evaluate()
    owner.kill()
    assert v.state == 'INVALID' and 'deadline' in v.reason, v
    ok, why = m.start_gate()
    assert not ok, why
    reset_runtime()
    return {'verdict': v.reason, 'gate': why}


@scenario
def s10_unrelated_sensor_recovery_continues(port):
    ensure_stage_a(port)
    restore_stage_b_baseline()
    reset_runtime()
    fresh_recovery()
    owner, m, s = arm_with_owner(120)
    lid0 = show('atlas-lidar.service', 'MainPID')['MainPID']
    (STATE / 'lidar_hb.stop').write_text('')
    ok = wait_for(lambda: show('atlas-lidar.service', 'MainPID')['MainPID'] != lid0, 25)
    owner.kill()
    reset_runtime()
    assert ok, 'recovery must still restart an unrelated stale sensor during a base hold'
    return {'lidar_pid': [lid0, show('atlas-lidar.service', 'MainPID')['MainPID']]}


@scenario
def s11_recovery_without_module_fails_closed(port):
    """Patched recovery whose module is missing + an existing lease -> base restart withheld."""
    ensure_stage_a(port)
    reset_runtime()
    mod = SCRIPTS / 'atlas_base_maintenance.py'
    keep = mod.read_bytes()
    owner, m, s = arm_with_owner(120)
    mod.unlink()
    try:
        fresh_recovery()
        t0 = time.time()
        world(encoder_state='CRITICAL')
        time.sleep(8)
        world(encoder_state='READY')
        lines = recovery_lines(t0 - 10)
    finally:
        mod.write_bytes(keep)
        os.chmod(mod, 0o644)
        owner.kill()
        reset_runtime()
        fresh_recovery()
    assert any('UNAVAILABLE' in x for x in lines) or any('module unavailable' in x for x in lines), lines[:5]
    assert not base_restart_by_recovery(lines), 'base restarted although the lease could not be evaluated'
    cancels = [x for x in lines if 'CANCELED' in x or 'HELD' in x or 'HOLD INVALID' in x]
    assert cancels, lines[:8]
    return {'lines': cancels[:3]}


@scenario
def s12_stop_guard_unchanged_without_lease(port):
    """No lease, stop guard broken: patched recovery still refuses a base restart (existing E-STOP rule)."""
    ensure_stage_a(port)
    reset_runtime()
    fresh_recovery()
    t0 = time.time()
    world(stop_latched=False, encoder_state='CRITICAL')
    time.sleep(8)
    world(stop_latched=True, encoder_state='READY')
    lines = recovery_lines(t0)
    assert not base_restart_by_recovery(lines)
    assert any('STOP REQUIRED' in x for x in lines), lines[:5]
    return {'line': next(x for x in lines if 'STOP REQUIRED' in x)}


@scenario
def s13_no_lease_recovery_unchanged(port):
    """No lease, stop guard satisfied: patched recovery performs its bounded base restart exactly as before."""
    ensure_stage_a(port)
    reset_runtime()
    fresh_recovery()
    t0 = time.time()
    world(encoder_state='CRITICAL')
    ok = wait_for(lambda: base_restart_by_recovery(recovery_lines(t0)), 15)
    world(encoder_state='READY')
    time.sleep(6)
    assert ok, 'patched recovery must keep its normal base recovery when no lease exists'
    return {'line': base_restart_by_recovery(recovery_lines(t0))[0]}


@scenario
def s14_estop_released_inside_stage_a_window(port):
    """E-STOP released 1 s after the recovery restart: the independent observer sees policy.stop_latched=false,
    stage A aborts immediately (not at window end) and the original recovery is restored."""
    install_original_recovery()
    reset_runtime()
    fresh_recovery()
    env = SimEnv(port, cpu={'transient_n': 2, 'transient_val': 98.8, 'steady': 66.0})
    orig = env.systemctl

    def trip(*a, **k):
        r = orig(*a, **k)
        if a[:2] == ('restart', REC):
            threading.Timer(1.0, lambda: world(stop_latched=False)).start()
        return r
    env.systemctl = trip
    t0 = time.time()
    try:
        rc = D.main(['install-recovery', '--cpu-rule', 'transient', '--transient-bound-s', '10',
                     '--owner-confirms-transmitter-off', '--owner-confirms-actuators-disconnected'], env=env)
    finally:
        world(stop_latched=True)
    ev = sorted((W / 'evidence').glob('stage28-recovery-coordination-*'))[-1]
    res = json.loads(sorted(ev.glob('*-result.json'))[-1].read_text())
    abort = json.loads(next(ev.glob('*-abort-A-post.json')).read_text())
    assert rc == 1 and res['result'] == 'FAIL', res
    assert any('estop_latched' in str(r) for r in abort['reasons']), abort['reasons']
    assert D.sha(SCRIPTS / 'atlas_sensor_recovery.py') == D.MANIFEST['modified']['atlas_sensor_recovery.py']['baseline_sha256']
    return {'reasons': abort['reasons'][:1], 'aborted_after_s': round(abort['cpu_samples_since_restart'][-1][0], 1),
            'total_s': round(time.time() - t0, 1)}


ALL = [s00_original_recovery_races_manual_restart, s00b_original_recovery_defers_during_long_init,
       s01_stage_a_install_recovery, s02_stage_a_strict_rule_rolls_back,
       s03_stage_b_deploy_happy_path_with_dds_gap, s04_inflight_recovery_restart_blocks_entry,
       s04b_deployer_waits_for_recovery_confirm_loop,
       s05_candidate_crash_rolls_back_without_loop, s06_cpu_never_settles_rolls_back,
       s07_stop_guard_broken_before_restart, s08_owner_crash_fails_closed_then_abandon,
       s09_expired_lease_stays_closed, s10_unrelated_sensor_recovery_continues,
       s11_recovery_without_module_fails_closed, s12_stop_guard_unchanged_without_lease,
       s13_no_lease_recovery_unchanged, s14_estop_released_inside_stage_a_window]


def main():
    workdir = sys.argv[1]
    want = set(sys.argv[2:])
    setup(workdir)
    shutil.copytree(SCRIPTS, W / 'baselines')
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Web)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    for s in ALL:
        if not want or s.__name__ in want or s.__name__.split('_')[0] in want:
            s(port)
    (W / 'results.json').write_text(json.dumps(RESULTS, indent=1))
    print('\nSUMMARY ' + ' '.join(f'{r["scenario"].split("_")[0]}={"PASS" if r["pass"] else "FAIL"}' for r in RESULTS))
    for s in [BASE, REC] + SENSORS + PROTECTED:
        sh('stop', s, check=False)
    return 0 if all(r['pass'] for r in RESULTS) else 1


if __name__ == '__main__':
    raise SystemExit(main())
