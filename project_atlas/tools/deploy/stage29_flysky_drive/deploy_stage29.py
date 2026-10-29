#!/usr/bin/env python3
"""ATLAS Stage 29 Stage A: supervised, per-step deployment of the FlySky driving integration WITH THE GATE OFF.

PROPOSAL. Every mutating action refuses unless OWNER_APPROVED=yes and the owner's explicit flags are given.
Nothing here enables FlySky driving: the deployer REFUSES if ATLAS_FLYSKY_DRIVE_ENABLED=1 is present anywhere, and it
verifies after every step that the gate is still off and the Xbox is still the selected controller.

Steps, in this fixed order, ONE per invocation, each with its own approval and its own CPU bound:
  mux    : patched atlas_cmd_vel_mux.py (built on the rover from the live file), restart atlas-cmd-vel-mux.
           During its restart the mux-owned observer signals (policy, /cmd_vel) are exempt for at most
           MUX_BACK_TIMEOUT_S; the base-owned signals (/motor_speed, encoder health, base loop, stillness,
           identity) stay strict: that is the independent proof that nothing moves while the mux is down.
  teleop : new drive core, teleop node, config (reviewed_by_owner=false) and unit (gate =0); start it once.
           It must log DISABLED and must not advertise /cmd_vel_flysky.
  web    : patched atlas_status_web.py, atlas_web_v2.py (+1 route), flysky.css, new endpoint module and page;
           restart rover-status-web. The observer is independent of the dashboard and is the in-window safety
           source; the dashboard's 14 predicates are checked before and after.

Monitoring (reused unchanged from the Stage 28 deployer): continuous 1-s CPU/RAM/temperature recorder and the
independent safety observer (0.25 s verdicts, 1.0 s freshness, 1.0 s gap limit), both started before the change,
every sample streamed to disk; pre-window strict check; immediate abort checks every 0.5 s.

Measured CPU recovery criteria per restart (limits 75 / 80 / 70 never change):
  * every sample before the restart <= 75 (else refused, nothing changed);
  * > 75 tolerated only inside the owner-approved bound for THAT service (no default; <= 30 s);
  * then STEADY_S consecutive samples all <= 75, RAM <= 80 and temperature < 70 on every sample;
  * steady-window mean <= pre-window mean + RECOVERY_MEAN_MARGIN (no lasting new load).

Failure handling:
  * safety failure (observer stale/unsafe, protected PID change, service not back, verification failed):
    automatic rollback of that step (restore backups, one restart, CPU recorded but not aborted), then stop;
  * CPU / RAM / temperature overrun with safety intact: FAIL and HOLD. No automatic restart, because a rollback
    restart repeats the same spike. Recording continues until CPU recovers; the owner decides on
    `rollback --step <step> --evidence <dir>`.
Never: firmware, serial, motor/steering commands, E-STOP reset, gate on, threshold changes, retries.
"""
import argparse
import json
import os
import shutil
import stat
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]                                      # .../project_atlas
sys.path.insert(0, str(HERE.parent / 'stage28_base_maintenance'))
sys.path.insert(0, str(HERE))
import deploy_rc_bridge as d28                              # noqa: E402  (reused, unchanged)
import insert_flysky_mux                                    # noqa: E402
import insert_status_web_hooks                              # noqa: E402

Fail = d28.Fail
CPU_LIMIT, RAM_LIMIT, TEMP_LIMIT = d28.CPU_LIMIT, d28.RAM_LIMIT, d28.TEMP_LIMIT
MANIFEST = json.loads((HERE / 'MANIFEST.json').read_text())
STEPS = ('mux', 'teleop', 'web')
UNITS = {'mux': 'atlas-cmd-vel-mux.service', 'teleop': 'atlas-flysky-teleop.service', 'web': 'rover-status-web.service'}
MUX_SIGNALS = ('estop_latched', 'manual_only', 'commission_off', 'source_stopped', 'cmd_zero')   # published by the mux
MUX_BACK_TIMEOUT_S = 20.0
RECOVERY_MEAN_MARGIN = 4.0
MAX_BOUND_S = d28.MAX_TRANSIENT_BOUND_S
HOLD_MAX_S = 180.0
GATE = 'ATLAS_FLYSKY_DRIVE_ENABLED'


class CpuOverrun(Fail):
    """Resource limit missed while every safety signal held: hold, never auto-restart."""


# ------------------------------------------------------------------ environment
class Env(d28.Env):
    def __init__(self, **kw):
        home = Path('/home/jetson')
        defaults = dict(project=home / 'project_atlas', unit_dir=home / '.config/systemd/user',
                        env_dir=home / '.config/project-atlas', evidence_root=home / 'project-atlas-migration',
                        pre_restart_s=10, steady_s=30, preflight_s=30, hold_poll_s=1.0, mux_back_timeout_s=MUX_BACK_TIMEOUT_S)
        defaults.update(kw)
        super().__init__(**defaults)
        self.scripts = self.project / 'scripts'
        self.protected = sorted(set(self.protected) | {UNITS['mux'], UNITS['web'], 'rover-base-telemetry.service',
                                                       'atlas-sensor-recovery.service', 'atlas-foxglove.service'})

    def get_text(self, path):
        with urllib.request.urlopen(self.api + path, timeout=3) as r:
            return r.status, r.read().decode('utf-8', 'replace')

    def unit_environment(self, unit):
        out = self.systemctl('show', unit, '-p', 'Environment', '-p', 'EnvironmentFiles', check=False).stdout
        return out

    def advertised_topics(self, seconds=2.5):
        """Topics the existing foxglove_bridge advertises (whitelist '.*'): read-only WebSocket, no ROS participant."""
        import atlas_safety_observer as so
        ws = None
        for proto in so.SUBPROTOCOLS:
            try:
                ws = so.WebSocket('127.0.0.1', self.observer_port, proto); break
            except Exception:
                continue
        if ws is None:
            raise Fail('foxglove bridge unreachable for the topic check')
        topics, end = set(), time.time() + seconds
        try:
            while time.time() < end:
                try:
                    op, data = ws.recv()
                except Exception:
                    continue
                if op == 0x1:
                    m = json.loads(data)
                    if m.get('op') == 'advertise':
                        topics |= {c.get('topic') for c in m.get('channels', [])}
        finally:
            ws.close()
        return topics


class Evidence(d28.Evidence):
    def __init__(self, env, kind):
        self.dir = env.evidence_root / f'stage29-{kind}-{time.strftime("%Y%m%d_%H%M%S")}-{time.time_ns() % 10**9:09d}'
        self.dir.mkdir(parents=True, exist_ok=False)
        self.n = 0


# ------------------------------------------------------------------ plan
def file_plan(env, step):
    """[(dst Path, bytes, mode, baseline_sha or None for a new file, candidate_sha)] built from the LIVE files."""
    plan = []
    for rel, spec in MANIFEST['steps'][step]['files'].items():
        dst = (env.unit_dir / Path(rel).name) if spec['kind'] == 'unit' else (env.project / rel)
        if spec['kind'] == 'patch':
            live = dst.read_text(encoding='utf-8')
            if d28.sha(dst) != spec['baseline_sha256']:
                raise Fail(f'{rel}: live file drifted from the reviewed baseline ({d28.sha(dst)[:12]}); nothing changed')
            mod = {'insert_flysky_mux.py': insert_flysky_mux, 'insert_status_web_hooks.py': insert_status_web_hooks}[spec['patcher']]
            data = mod.apply(live).encode('utf-8')
        else:
            src = REPO / spec['source']
            data = src.read_bytes()
            if spec['kind'] == 'replace' and d28.sha(dst) != spec['baseline_sha256']:
                raise Fail(f'{rel}: live file drifted from the reviewed baseline ({d28.sha(dst)[:12]}); nothing changed')
            if spec['kind'] in ('new', 'unit') and dst.exists():
                raise Fail(f'{rel}: already present on the rover; refusing to overwrite an unreviewed file')
        import hashlib
        got = hashlib.sha256(data).hexdigest()
        if got != spec['candidate_sha256']:
            raise Fail(f'{rel}: candidate hash {got[:12]} != reviewed {spec["candidate_sha256"][:12]}')
        if dst.suffix == '.py':
            compile(data, str(dst), 'exec')
        mode = stat.S_IMODE(os.stat(dst).st_mode) if dst.exists() else 0o644    # new files: run via python3, never exec bit
        plan.append((dst, data, mode, spec.get('baseline_sha256'), got))
    return plan


def step_done(env, step):
    for rel, spec in MANIFEST['steps'][step]['files'].items():
        dst = (env.unit_dir / Path(rel).name) if spec['kind'] == 'unit' else (env.project / rel)
        if not dst.exists() or d28.sha(dst) != spec['candidate_sha256']:
            return False
    return True


def backup(env, ev, plan):
    bk = ev.dir / 'backup'
    bk.mkdir()
    meta = {}
    for i, (dst, _, _, _, _) in enumerate(plan):
        key = f'{i:02d}-{dst.name}'
        if dst.exists():
            shutil.copy2(dst, bk / key)
            if d28.sha(bk / key) != d28.sha(dst):
                raise Fail(f'backup verification failed for {dst}')
            meta[key] = {'dst': str(dst), 'present': True, 'sha256': d28.sha(dst), 'mode': stat.S_IMODE(os.stat(dst).st_mode)}
        else:
            meta[key] = {'dst': str(dst), 'present': False}
    (bk / 'meta.json').write_text(json.dumps(meta, indent=1))
    ev.log('backup ' + json.dumps({m['dst'].split('/')[-1]: m.get('sha256', 'absent')[:12] for m in meta.values()}))
    return meta


def restore(env, ev, bkdir, meta):
    for key, m in meta.items():
        dst = Path(m['dst'])
        if m['present']:
            d28.install_atomic((bkdir / key).read_bytes(), dst, m['mode'])
            if d28.sha(dst) != m['sha256']:
                raise Fail(f'restore hash mismatch {dst}')
        elif dst.exists():
            dst.unlink()
    ev.log('restored: ' + ', '.join(f'{Path(m["dst"]).name}={"restored" if m["present"] else "removed"}' for m in meta.values()))


# ------------------------------------------------------------------ gates
def policy(env):
    r = env.get('/api/status')['ros']['control_policy']
    if not (type(r.get('age')) in (int, float) and 0 <= r['age'] <= 1.0):
        raise Fail(f'control policy stale (age {r.get("age")})')
    v = r['value']
    return json.loads(v) if isinstance(v, str) else v


def require_gate_off(env, ev):
    found = []
    for unit in (UNITS['mux'], UNITS['teleop']):
        if f'{GATE}=1' in env.unit_environment(unit):
            found.append(unit + ' Environment')
    for f in (Path(env.env_dir) / 'hardware.env', Path(env.env_dir) / 'flysky-drive.env'):   # never credential files
        if not f.exists():
            continue
        try:
            if any(line.strip().replace(' ', '') == f'{GATE}=1' for line in f.read_text().splitlines()):
                found.append(str(f))
        except OSError as exc:
            raise Fail(f'cannot read {f}: {exc}')
    if found:
        raise Fail(f'FlySky driving gate is ON in {found}; Stage A deploys only with the gate off')
    ev.log('gate off: no ' + GATE + '=1 in the mux/teleop environment or ' + str(env.env_dir))


def require_order(env, step):
    i = STEPS.index(step)
    if step_done(env, step):
        raise Fail(f'step {step} is already installed; nothing to do')
    for prev in STEPS[:i]:
        if not step_done(env, prev):
            raise Fail(f'step {step} needs step {prev} first (order: {" -> ".join(STEPS)})')


def preconditions(env, ev, step):
    require_order(env, step)
    require_gate_off(env, ev)
    est = env.get('/api/estop/state')
    if est.get('latched') is not True:
        raise Fail('E-STOP is not latched; latch it (Xbox B) before any Stage A step')
    p = policy(env)
    if p.get('manual_controller', 'XBOX') != 'XBOX' or p.get('flysky_drive_enabled') is True:
        raise Fail(f'unexpected controller policy {p}')
    d28.require_safe(env, ev, f'{step}-pre', count=3)
    d28.resources_strict(env, ev, f'{step}-preflight', env.preflight_s)


def recovery_mean(ev, label, rec, t_restart, bound_s):
    pre = [x for ts, x in list(rec.samples) if ts <= t_restart]
    after = [x for d, x in rec.timed_since(t_restart) if d > bound_s]
    if not pre or not after:
        raise CpuOverrun(f'{label}: not enough samples for the recovery comparison')
    pm, am = sum(pre) / len(pre), sum(after) / len(after)
    ev.save(f'recovery-mean-{label}', {'pre_mean': round(pm, 2), 'steady_mean': round(am, 2), 'margin': RECOVERY_MEAN_MARGIN})
    if am > pm + RECOVERY_MEAN_MARGIN:
        raise CpuOverrun(f'{label}: steady CPU mean {am:.1f} % > pre-window {pm:.1f} % + {RECOVERY_MEAN_MARGIN} (lasting new load)')
    ev.log(f'{label}: CPU recovered: steady mean {am:.1f} % vs pre-window {pm:.1f} %')


def classify(rec, obs, t_restart, bound_s):
    """Re-derive WHY a window failed from the raw recorders (never from message text)."""
    now = time.time()
    safety = obs.failures(t_restart, now) if obs is not None else []
    walls = [t_restart] + [s['wall'] for s in list(getattr(obs, 'snaps', [])) if s['wall'] > t_restart] + [now]
    gap = max((b - a for a, b in zip(walls, walls[1:])), default=0.0)
    return bool(safety) or gap > getattr(obs, 'max_gap_s', 1.0)


OBSERVER_BACK_S = 1.0            # the observer itself must see the mux signals fresh and OK this long


def observer_mux_ok_since(obs, t0):
    """Start of the latest continuous stretch (after t0) in which the OBSERVER reports every mux-owned signal OK."""
    since = None
    for s in reversed([x for x in list(obs.snaps) if x['wall'] > t0]):
        if all(s.get('predicates', {}).get(k) is True for k in MUX_SIGNALS):
            since = s['wall']
        else:
            break
    return since


def wait_mux_back(env, ev, obs, rec, t0, bound_s):
    """Mux-owned observer signals are exempt while the mux restarts. The exemption is cleared only when BOTH the
    dashboard shows the patched policy AND the observer's own verdicts show every mux-owned signal fresh and OK for
    OBSERVER_BACK_S (A1 attempt 1, 2026-10-29: clearing it on the dashboard alone aborted on the foxglove bridge's
    re-subscription lag). Never clear an exemption on a different source than the one being judged."""
    deadline = time.time() + env.mux_back_timeout_s
    dash = None
    while time.time() < deadline:
        d28.early_abort(env, ev, 'mux-back', rec, t0, bound_s, obs)
        if dash is None:
            try:
                p = policy(env)
                if 'manual_controller' in p:
                    dash = (time.time(), p)
                    ev.log(f'mux back on the dashboard after {dash[0] - t0:.1f} s: {p}')
            except Exception:
                pass
        since = observer_mux_ok_since(obs, t0)
        if dash and since is not None and time.time() - since >= OBSERVER_BACK_S:
            obs.exempt.clear()
            ev.log(f'observer sees the mux signals fresh since +{since - t0:.1f} s; exemption cleared at +{time.time() - t0:.1f} s')
            return dash[1]
        env.sleep(0.25)
    raise Fail(f'mux not back within {env.mux_back_timeout_s} s (dashboard {"yes" if dash else "no"}, '
               f'observer mux signals {"ok" if observer_mux_ok_since(obs, t0) else "not ok"})')


def verify(env, ev, step, before, protected0):
    unit = UNITS[step]
    s = d28.require_running(env, unit)
    if step != 'teleop' and s.get('MainPID') == before.get('MainPID'):
        raise Fail(f'{unit} PID did not change ({s.get("MainPID")}): restart not effective')
    log = env.journal(s.get('InvocationID'))
    if 'Traceback' in log:
        raise Fail(f'{unit}: traceback in the new invocation journal')
    changed = {u: (a, d28.identities(env, [u])[u]) for u, a in protected0.items() if d28.identities(env, [u])[u] != a}
    if changed:
        raise Fail(f'protected service identity changed: {changed}')
    p = policy(env)
    if not (p.get('stop_latched') is True and p.get('manual_controller') == 'XBOX'
            and p.get('flysky_drive_enabled') is False and p.get('source') == 'STOPPED'):
        raise Fail(f'post-{step} policy not as required (latched, XBOX, gate off, STOPPED): {p}')
    if step == 'mux' and 'FLYSKY' not in log:
        raise Fail('mux journal does not show the FLYSKY channel in its priority line')
    if step == 'teleop':
        if 'FlySky teleop DISABLED' not in log:
            raise Fail('teleop did not report DISABLED')
        topics = env.advertised_topics()
        if '/cmd_vel_flysky' in topics:
            raise Fail('/cmd_vel_flysky is advertised: the disabled teleop must not create a command publisher')
        if '/atlas/flysky/drive_status' not in topics:
            raise Fail('teleop status topic not advertised')
    if step == 'web':
        v = env.get('/api/manual_controller')
        pol, drv = v.get('policy', {}), v.get('drive', {})
        if not (pol.get('selection_supported') is True and pol.get('manual_controller') == 'XBOX'
                and pol.get('flysky_drive_enabled') is False and v.get('can_select', {}).get('FLYSKY') is False):
            raise Fail(f'/api/manual_controller not as required: {v}')
        if not (drv.get('running') is True and (drv.get('status') or {}).get('state') == 'DISABLED'):
            raise Fail(f'dashboard does not show the teleop as running and DISABLED: {drv}')
        code, html = env.get_text('/v2/flysky-drive')
        if code != 200 or 'FlySky Driving' not in html:
            raise Fail(f'/v2/flysky-drive not served ({code})')
        lab = env.get('/api/flysky/state')
        if lab.get('read_only') is not True or 'link' not in lab:
            raise Fail('FlySky Test Lab API changed or unavailable')
    ev.log(f'{step}: verified {unit} pid {s.get("MainPID")}; policy {p}')


# ------------------------------------------------------------------ actions
def deploy_step(env, args, ev=None):
    step, unit = args.step, UNITS[args.step]
    ev = ev or Evidence(env, f'deploy-{step}')
    ev.log(f'STAGE 29 STAGE A step {step}: bound {args.cpu_bound_s} s; gate stays OFF; no motion is commanded')
    state = {'installed': False, 'restarted': False}
    try:
        preconditions(env, ev, step)
        plan = file_plan(env, step)
        meta = backup(env, ev, plan)
        before = d28.unit_state(env, unit)
        protected0 = d28.identities(env, [u for u in env.protected if u != unit])
        base_pid = int(d28.unit_state(env, 'rover-base-telemetry.service').get('MainPID', '0'))
    except Fail as exc:
        ev.log(f'REFUSED, nothing changed: {exc}')
        ev.save('result', {'result': 'REFUSED_NO_CHANGE', 'reason': str(exc)}); ev.seal()
        return 3
    rec = obs = None
    t0 = None
    try:
        with d28.CpuRecorder(env, sink=ev.stream(f'cpu-{step}')) as rec, \
                d28.ObserverRecorder(env, base_pid, sink=ev.stream(f'observer-{step}')) as obs:
            env.sleep(2.5)
            d28.require_pre_window_ok(env, ev, step, rec, obs)
            for dst, data, mode, _, _ in plan:
                dst.parent.mkdir(parents=True, exist_ok=True)
                d28.install_atomic(data, dst, mode)
            state['installed'] = True
            ev.log('installed: ' + ', '.join(f'{dst.name}={h[:12]}' for dst, _, _, _, h in plan))
            if step == 'teleop':
                env.systemctl('daemon-reload', timeout=30)
            if step == 'mux':
                obs.exempt.update(MUX_SIGNALS)
            t0 = time.time()
            ev.log(f'{"starting" if step == "teleop" else "restarting"} {unit} ONLY')
            env.systemctl('start' if step == 'teleop' else 'restart', unit, timeout=60)
            state['restarted'] = True
            if step == 'mux':
                wait_mux_back(env, ev, obs, rec, t0, args.cpu_bound_s)
            try:
                d28.resources_after_restart(env, ev, f'{step}-post', 'transient', rec, t0, args.cpu_bound_s, obs)
            except Fail as exc:
                if classify(rec, obs, t0, args.cpu_bound_s):
                    raise
                raise CpuOverrun(str(exc)) from exc
            recovery_mean(ev, step, rec, t0, args.cpu_bound_s)
            ev.save(f'cpu-recorder-{step}', {'t_restart': t0, 'samples': rec.samples, 'ram_temp': rec.rt})
        verify(env, ev, step, before, protected0)
        d28.require_safe(env, ev, f'{step}-post', count=3)
        ev.log(f'STEP {step} PASS (gate off; Xbox selected; E-STOP latched)')
        ev.save('result', {'result': 'PASS', 'step': step}); ev.seal()
        return 0
    except CpuOverrun as exc:
        ev.log(f'STEP {step} FAILED on resources with safety intact: {exc}')
        hold(env, ev, step, rec, t0)
        ev.log(f'HELD: no automatic restart. Rollback on owner decision: rollback --step {step} --evidence {ev.dir}')
        ev.save('result', {'result': 'FAIL_HELD', 'step': step, 'reason': str(exc), 'rollback_evidence': str(ev.dir)}); ev.seal()
        return 1
    except Exception as exc:
        if not state['installed']:
            ev.log(f'REFUSED before any change: {exc!r}')
            ev.save('result', {'result': 'REFUSED_NO_CHANGE', 'step': step, 'reason': repr(exc)}); ev.seal()
            return 3
        ev.log(f'STEP {step} FAILED (safety/verification): {exc!r}; rolling back')
        try:
            if state['installed']:
                rollback_files(env, ev, step, ev.dir / 'backup', meta, restart=state['restarted'])
            ev.save('result', {'result': 'FAIL_ROLLED_BACK', 'step': step, 'reason': repr(exc)})
        except Exception as rb:
            ev.log(f'ROLLBACK NOT CONFIRMED ({rb!r}): owner inspection required; no further restart attempted')
            ev.save('result', {'result': 'FAIL_ROLLBACK_UNCONFIRMED', 'step': step, 'reason': repr(exc), 'rollback': repr(rb)})
        ev.seal()
        return 1


def hold(env, ev, step, rec, t0):
    """Keep recording (no restart) until CPU is back under the limit for steady_s samples, or HOLD_MAX_S."""
    with d28.CpuRecorder(env, sink=ev.stream(f'cpu-hold-{step}')) as r:
        deadline = time.time() + HOLD_MAX_S
        while time.time() < deadline:
            s = [x for _, x in list(r.samples)][-env.steady_s:]
            if len(s) >= env.steady_s and max(s) <= CPU_LIMIT:
                ev.log(f'hold: CPU back <= {CPU_LIMIT} for {env.steady_s} samples'); return
            env.sleep(env.hold_poll_s)
    ev.log(f'hold: CPU did not recover within {HOLD_MAX_S} s; owner inspection required')


def rollback_files(env, ev, step, bkdir, meta, restart=True):
    unit = UNITS[step]
    with d28.CpuRecorder(env, sink=ev.stream(f'cpu-rollback-{step}')) as rec:
        t = time.time()
        if step == 'teleop':
            env.systemctl('stop', unit, timeout=60, check=False)
            restore(env, ev, bkdir, meta)
            env.systemctl('daemon-reload', timeout=30)
        else:
            restore(env, ev, bkdir, meta)
            if restart:
                d28.wait_quiescent(env, unit)
                env.systemctl('restart', unit, timeout=60)
                d28.require_running(env, unit)
        env.sleep(env.steady_s)
        d28.record_rollback_cpu(env, ev, step, rec, t)
    ev.log(f'ROLLBACK of {step} complete')


def rollback(env, args):
    ev = Evidence(env, f'rollback-{args.step}')
    src = Path(args.evidence)
    meta = json.loads((src / 'backup' / 'meta.json').read_text())
    try:
        require_latched(env)
    except Exception as exc:
        ev.log(f'REFUSED: {exc}'); ev.seal(); return 3
    rollback_files(env, ev, args.step, src / 'backup', meta, restart=True)
    ev.save('result', {'result': 'ROLLED_BACK', 'step': args.step, 'from': str(src)}); ev.seal()
    return 0


def require_latched(env):
    if env.get('/api/estop/state').get('latched') is not True:
        raise Fail('E-STOP not latched')


def preflight(env, args):
    ev = Evidence(env, 'preflight')
    ok = True
    for step in STEPS:
        try:
            if step_done(env, step):
                ev.log(f'step {step}: INSTALLED')
            else:
                file_plan(env, step)
                ev.log(f'step {step}: candidates rebuilt from live files, all hashes match')
        except Fail as exc:
            ok = False
            ev.log(f'step {step}: {exc}')
    for label, fn in (('gate', lambda: require_gate_off(env, ev)),
                      ('estop', lambda: require_latched(env)),
                      ('safety', lambda: d28.require_safe(env, ev, 'preflight')),
                      ('resources', lambda: d28.resources_strict(env, ev, 'preflight', env.preflight_s))):
        try:
            fn()
        except Exception as exc:
            ok = False
            ev.log(f'{label}: {exc}')
    ev.save('result', {'result': 'GO' if ok else 'NO-GO'}); ev.seal()
    return 0 if ok else 1


def main(argv=None, env=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('action', choices=['preflight', 'deploy', 'rollback'])
    p.add_argument('--step', choices=STEPS)
    p.add_argument('--cpu-bound-s', type=float, help='owner-approved transient bound for THIS step (no default)')
    p.add_argument('--evidence', help='rollback: the evidence directory of the step being undone')
    p.add_argument('--owner-confirms-estop-latched', action='store_true')
    p.add_argument('--owner-confirms-rover-lifted-and-clear', action='store_true')
    p.add_argument('--evidence-root')
    a = p.parse_args(argv)
    env = env or Env(**({'evidence_root': Path(a.evidence_root)} if a.evidence_root else {}))
    if a.action == 'preflight':
        return preflight(env, a)
    if os.environ.get('OWNER_APPROVED') != 'yes':
        print('refused: OWNER_APPROVED=yes required (separate owner approval)'); return 2
    if not (a.step and a.owner_confirms_estop_latched and a.owner_confirms_rover_lifted_and_clear):
        print('refused: --step and both owner confirmations are required'); return 2
    if a.action == 'rollback':
        if not a.evidence:
            print('refused: --evidence required'); return 2
        return rollback(env, a)
    if a.cpu_bound_s is None or not 0 < a.cpu_bound_s <= MAX_BOUND_S:
        print(f'refused: --cpu-bound-s must be given explicitly, 0 < bound <= {MAX_BOUND_S}'); return 2
    return deploy_step(env, a)


if __name__ == '__main__':
    sys.exit(main())
