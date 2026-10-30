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
  view   : (UI only, optional) dual-controller dashboard: one additive import + GET route in the A3 status web, the
           read-only live Xbox input module, the controller visualisation page files; restart rover-status-web.
           Chained on A3 (its baselines are the A3 candidates). Never required for driving (gate-on ignores it).
  features: lease-aware atlas_feature_on_demand.py (an authorised restart no longer looks like an autonomy request,
           and restore-all is skipped under a valid lease); restart atlas-feature-on-demand under the lease, verify
           that no managed feature started. Required before gate-on (its mux restart otherwise starts 5 AI services).
  reset  : (2026-10-30, separate approval, gate ON) FlySky SwD (CH8) E-STOP reset: new atlas_flysky_reset.py, the
           reset-patched mux (over the deployed Stage 29 mux), the reset-aware teleop and page files, plus a RUNTIME
           drop-in ATLAS_FLYSKY_RESET_ENABLED=1 for the mux and the teleop; ONE mux restart under the lease (the
           teleop follows via PartOf); the new mux is proven by policy flysky_reset.enabled True. After a reboot the
           drop-in is gone (like the gate): gate-on, then `deploy --step reset` again re-enables it without copying
           files. gate-off removes it. It can only RELEASE a latched E-STOP after the full SwD gesture and every mux
           check; it never commands motion. See scripts/atlas_flysky_reset.py.

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
import contextlib
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
import insert_controller_input_hooks                        # noqa: E402
import insert_flysky_reset_mux                             # noqa: E402
sys.path.insert(0, str(REPO / 'scripts'))

Fail = d28.Fail
CPU_LIMIT, RAM_LIMIT, TEMP_LIMIT = d28.CPU_LIMIT, d28.RAM_LIMIT, d28.TEMP_LIMIT
MANIFEST = json.loads((HERE / 'MANIFEST.json').read_text())
STEPS = ('mux', 'teleop', 'web', 'view', 'features')
RESET_STEP = 'reset'                               # gate-ON step with its own action path (deploy_reset)
ALL_STEPS = STEPS + (RESET_STEP,)
REQUIRED_STEPS = ('mux', 'teleop', 'web')          # what FlySky driving needs; 'view' is the optional dashboard UI
UNITS = {'mux': 'atlas-cmd-vel-mux.service', 'teleop': 'atlas-flysky-teleop.service', 'web': 'rover-status-web.service',
         'view': 'rover-status-web.service', 'features': 'atlas-feature-on-demand.service', 'reset': 'atlas-cmd-vel-mux.service'}
LEASED_STEPS = ('mux', 'features')       # restarts that run under the authorised-restart lease
MANAGED_FEATURES = ('atlas-vision-lidar-fusion', 'atlas-person-sensor-fusion', 'atlas-experience-store', 'atlas-agent-team',
                    'atlas-ai-annotator', 'atlas-follow-person', 'atlas-camera-tracker', 'atlas-active-vision')
DASHBOARD_STEPS = ('web', 'view')
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
        """Topics the existing foxglove_bridge advertises (whitelist '.*'): read-only WebSocket, no ROS participant.
        The observer's WebSocket blocks indefinitely after the handshake (correct for its own reader thread), and the
        bridge advertises once then goes quiet, so reading happens in a daemon thread with a hard deadline and the
        socket is closed afterwards (found in the A2 readiness check, 2026-10-29). No advertisement at all = Fail:
        an empty set would make "/cmd_vel_flysky not advertised" meaningless."""
        import atlas_safety_observer as so
        import threading
        ws = None
        for proto in so.SUBPROTOCOLS:
            try:
                ws = so.WebSocket('127.0.0.1', self.observer_port, proto); break
            except Exception:
                continue
        if ws is None:
            raise Fail('foxglove bridge unreachable for the topic check')
        topics, seen = set(), threading.Event()

        def reader():
            try:
                while True:
                    op, data = ws.recv()
                    if op == 0x1:
                        m = json.loads(data)
                        if m.get('op') == 'advertise':
                            topics.update(c.get('topic') for c in m.get('channels', []))
                            seen.set()
            except Exception:
                return
        t = threading.Thread(target=reader, name='s29-advertise', daemon=True)
        t.start()
        t.join(seconds)
        ws.close()                                # unblocks the reader
        t.join(1.0)
        if not seen.is_set():
            raise Fail(f'no advertisement received from the foxglove bridge in {seconds} s')
        return set(topics)


    def sample_topics(self, wanted, seconds=3.0):
        """Subscribe through the existing foxglove_bridge (read-only, no ROS participant) and count messages per topic.
        A topic can be advertised with no publisher (the patched mux SUBSCRIBES to /cmd_vel_flysky, and the bridge
        lists every graph topic: found live in the A2 readiness check), so 'no publisher' is proven by receiving NO
        messages, never by the topic being absent. Returns {topic: {'advertised', 'count', 'last'}}."""
        import atlas_safety_observer as so
        import struct as _st
        import threading
        ws = None
        for proto in so.SUBPROTOCOLS:
            try:
                ws = so.WebSocket('127.0.0.1', self.observer_port, proto); break
            except Exception:
                continue
        if ws is None:
            raise Fail('foxglove bridge unreachable for the topic sample')
        out = {t: {'advertised': False, 'count': 0, 'last': None, 'schema': None} for t in wanted}
        subs, seen = {}, threading.Event()

        def reader():
            try:
                while True:
                    op, data = ws.recv()
                    if op == 0x1:
                        m = json.loads(data)
                        if m.get('op') != 'advertise':
                            continue
                        seen.set()
                        new = []
                        for ch in m.get('channels', []):
                            t = ch.get('topic')
                            if t in out and not out[t]['advertised']:
                                out[t].update(advertised=True, schema=ch.get('schemaName'))
                                sid = len(subs) + 1
                                subs[sid] = t
                                new.append({'id': sid, 'channelId': ch['id']})
                        if new:
                            ws.send(0x1, json.dumps({'op': 'subscribe', 'subscriptions': new}).encode())
                    elif data and data[0] == 0x01 and len(data) >= 13:
                        sid = _st.unpack_from('<I', data, 1)[0]
                        t = subs.get(sid)
                        if t is None:
                            continue
                        out[t]['count'] += 1
                        try:
                            out[t]['last'] = so.decode(out[t]['schema'], data[13:])
                        except Exception as exc:
                            out[t]['last'] = f'undecodable: {exc}'
            except Exception:
                return
        th = threading.Thread(target=reader, name='s29-sample', daemon=True)
        th.start()
        th.join(seconds)
        ws.close()
        th.join(1.0)
        if not seen.is_set():
            raise Fail(f'no advertisement received from the foxglove bridge in {seconds} s')
        return out


class Evidence(d28.Evidence):
    def __init__(self, env, kind):
        t = time.time_ns()          # ONE clock read: seconds and nanoseconds must agree or names sort out of order
        self.dir = env.evidence_root / f'stage29-{kind}-{time.strftime("%Y%m%d_%H%M%S", time.localtime(t // 10**9))}-{t % 10**9:09d}'
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
            mod = {'insert_flysky_mux.py': insert_flysky_mux, 'insert_status_web_hooks.py': insert_status_web_hooks,
                   'insert_controller_input_hooks.py': insert_controller_input_hooks,
                   'insert_flysky_reset_mux.py': insert_flysky_reset_mux}[spec['patcher']]
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


def step_done(env, step, ignore=()):
    """Every file of `step` is at its reviewed candidate hash. A file that a LATER step also writes is checked by that
    later step instead, when the later step is installed (the 'view' step replaces A3 page files; its baselines are the
    A3 candidates, so the chain is exact)."""
    superseded = set()
    for later in ALL_STEPS[ALL_STEPS.index(step) + 1:]:
        if step_done(env, later, ignore):
            superseded |= set(MANIFEST['steps'][later]['files'])
    for rel, spec in MANIFEST['steps'][step]['files'].items():
        if rel in ignore or rel in superseded:
            continue
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


def installed(env, step):
    """step_done, accepting the config only when it is EXACTLY the owner-reviewed commissioning config."""
    return step_done(env, step, ignore=(CONFIG_REL,) if reviewed_config_ok(env) else ())


def require_order(env, step):
    i = STEPS.index(step)
    if step_done(env, step):
        raise Fail(f'step {step} is already installed; nothing to do')
    for prev in STEPS[:i]:
        if not installed(env, prev):
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
    after_a3 = STEPS.index(step) > STEPS.index('web')      # the dashboard has run since the A3 restart
    (require_safe_after_dashboard_restart if after_a3 else d28.require_safe)(env, ev, f'{step}-pre', count=3)
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
# After the NEW mux is proven on the dashboard, the observer's OK stretch must start after that moment and last longer
# than the observer's 1.0 s freshness window, so a message cached from the OLD mux can never satisfy it.
OBSERVER_NEW_MUX_S = 1.5


def observer_mux_ok_since(obs, t0):
    """Start of the latest continuous stretch (after t0) in which the OBSERVER reports every mux-owned signal OK."""
    since = None
    for s in reversed([x for x in list(obs.snaps) if x['wall'] > t0]):
        if all(s.get('predicates', {}).get(k) is True for k in MUX_SIGNALS):
            since = s['wall']
        else:
            break
    return since


def wait_mux_back(env, ev, obs, rec, t0, bound_s, expect=None, what='the patched policy'):
    """Mux-owned observer signals are exempt while the mux restarts. The exemption is cleared only when BOTH the
    dashboard shows the patched policy AND the observer's own verdicts show every mux-owned signal fresh and OK for
    OBSERVER_BACK_S (A1 attempt 1, 2026-10-29: clearing it on the dashboard alone aborted on the foxglove bridge's
    re-subscription lag). Never clear an exemption on a different source than the one being judged.
    gate-on attempt 1 (2026-10-29 15:51): the OLD mux kept publishing for about 1 s after the restart command, and
    'manual_controller' is in both old and new policies, so stale old-mux data cleared the exemption at +1.4 s. The
    restarted mux must now be PROVEN by `expect` (for gate-on: flysky_drive_enabled True, which the old mux never
    reported), and the observer's OK stretch must begin after that proof and last OBSERVER_NEW_MUX_S."""
    expect = expect or (lambda p: 'manual_controller' in p)
    deadline = time.time() + env.mux_back_timeout_s
    dash = None
    while time.time() < deadline:
        # Safety failures, unreliable monitoring and RAM/temperature still abort at once (fail closed). The CPU bound
        # is judged separately so a CPU-only overrun can HOLD instead of a rollback restart (gate-on attempt 2: the
        # rollback restart repeated the spike for about 30 s).
        d28.early_abort(env, ev, 'mux-back', rec, t0, float('inf'), obs)
        late = [(d, x) for d, x in rec.timed_since(t0) if d > bound_s and x > CPU_LIMIT]
        if late:
            cpu_only_overrun(ev, 'mux-back', obs, rec, t0, bound_s, late, dash)
        if dash is None:
            try:
                p = policy(env)
                if expect(p):
                    dash = (time.time(), p)
                    ev.log(f'new mux proven on the dashboard ({what}) after {dash[0] - t0:.1f} s: {p}')
            except Exception:
                pass
        since = observer_mux_ok_since(obs, dash[0]) if dash else None
        if dash and since is not None and time.time() - since >= OBSERVER_NEW_MUX_S:
            obs.exempt.clear()
            ev.log(f'observer sees the mux signals fresh since +{since - t0:.1f} s; exemption cleared at +{time.time() - t0:.1f} s')
            return dash[1]
        env.sleep(0.25)
    raise Fail(f'mux not back within {env.mux_back_timeout_s} s (dashboard {"proved " + what if dash else "did not show " + what}, '
               f'observer mux signals {"ok" if dash and observer_mux_ok_since(obs, dash[0]) else "not ok"} after that)')


MUX_LEASE_S = 240.0            # upper bound of one mux-restart window (the Stage 28 lease format allows <= 600 s)


def mux_lease_root(env):
    return Path(getattr(env, 'mux_lease_root', None) or f'/run/user/{os.getuid()}/atlas-mux-maintenance')


@contextlib.contextmanager
def mux_lease(env, ev, purpose, active=True):
    """Authorised-mux-restart lease (Stage 28 atlas_base_maintenance format, own tmpfs root) held for exactly one
    reviewed mux restart window. While it is VALID, atlas_feature_on_demand treats a stale control policy as the
    restart it is, not as an autonomy request (gate-on attempts 1-2: five AI/fusion services started mid-restart).
    It is bound to this process: if the deployer dies the lease turns INVALID and the feature manager falls back to
    today's fail-open behaviour. Always released, also on failure."""
    if not active:
        yield None
        return
    import atlas_base_maintenance as bm
    m = bm.Maintenance(root=mux_lease_root(env))
    try:
        session = m.arm(purpose, MUX_LEASE_S)
    except bm.Refused as exc:
        raise Fail(f'mux maintenance lease not armed: {exc}') from exc
    ev.log(f'mux maintenance lease armed ({purpose}; at most {MUX_LEASE_S:.0f} s)')
    try:
        yield session
    finally:
        try:
            m.release(session)
            m.clear(session)
            ev.log('mux maintenance lease released')
        except Exception as exc:
            ev.log(f'mux maintenance lease NOT released ({exc!r}): it turns INVALID when this process exits '
                   f'or at its deadline, and the feature manager then behaves exactly as before')


def observer_healthy_since(obs, since):
    """The observer is producing verdicts (no gap over its limit from `since` to now) and none failed."""
    now = time.time()
    snaps = [x for x in list(getattr(obs, 'snaps', [])) if x['wall'] > since]
    walls = [since] + [x['wall'] for x in snaps] + [now]
    gap = max((b - a for a, b in zip(walls, walls[1:])), default=0.0)
    return bool(snaps) and gap <= getattr(obs, 'max_gap_s', 1.0) and not obs.failures(since, now)


def cpu_only_overrun(ev, label, obs, rec, t0, bound_s, late, dash):
    """CPU is over the limit after the approved bound. HOLD (CpuOverrun) only when every independent safety check is
    positively healthy: the NEW mux is proven on the dashboard, the observer has itself seen every mux-owned signal OK
    since that proof, and the observer has produced verdicts without a gap or any failure since the restart. Anything
    less (mux unproven, observer silent/unresponsive, any failure) is not CPU-only: fail closed (Fail -> rollback)."""
    msg = f'{label}: CPU > {CPU_LIMIT} after the {bound_s} s bound: {late[:3]}'
    proven = dash is not None and observer_mux_ok_since(obs, dash[0]) is not None
    if proven and observer_healthy_since(obs, t0) and not classify(rec, obs, t0, bound_s):
        ev.save(f'cpu-only-{label}', {'t_restart': t0, 'late': late, 'mux_proven_at': dash[0] - t0,
                                       'cpu_samples_since_restart': rec.timed_since(t0)})
        raise CpuOverrun(msg + '; new mux proven and every independent safety check healthy')
    raise Fail(msg + ('; observer not healthy' if proven else '; new mux not yet proven by the dashboard and observer'))


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
        smp = env.sample_topics(['/cmd_vel_flysky', '/atlas/flysky/drive_status'], seconds=3.0)
        ev.save('teleop-topic-sample', smp)
        if smp['/cmd_vel_flysky']['count'] > 0:
            raise Fail(f'{smp["/cmd_vel_flysky"]["count"]} message(s) on /cmd_vel_flysky: the disabled teleop must publish nothing')
        st = smp['/atlas/flysky/drive_status']
        if st['count'] == 0:
            raise Fail('teleop status not received through the bridge')
        try:
            state = json.loads(st['last']).get('state')
        except (TypeError, ValueError):
            state = None
        if state != 'DISABLED':
            raise Fail(f'teleop reports state {state!r}, required DISABLED')
    if step in DASHBOARD_STEPS:
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
    if step == 'features':
        if '"event": "start"' not in log:
            raise Fail('feature manager did not log its start')
        started = [l for l in log.splitlines() if '"event": "start", "unit"' in l]
        if started:
            raise Fail(f'feature manager started managed features during the authorised restart: {started[:3]}')
        now_states = {u: d28.unit_state(env, u + '.service').get('ActiveState') for u in MANAGED_FEATURES}
        if now_states != before.get('features', now_states):
            raise Fail(f'managed feature states changed during the restart: {before.get("features")} -> {now_states}')
    if step == 'view':
        ci = env.get('/api/controller_inputs')
        xb = ci.get('xbox') or {}
        if ci.get('read_only') is not True or xb.get('state') not in ('LIVE', 'STALE', 'LOST', 'NO_DATA'):
            raise Fail(f'/api/controller_inputs not as required: {ci}')
        if xb.get('state') == 'LIVE' and xb.get('layout_ok') is not True:
            raise Fail(f'Xbox /joy layout differs from the verified 8 axes / 11 buttons: {xb}')
        if 'controller-viz.js' not in html or 'SELECT FLYSKY' not in html:
            raise Fail('/v2/flysky-drive is not the dual-controller page')
        ev.save('view-controller-inputs', ci)
    ev.log(f'{step}: verified {unit} pid {s.get("MainPID")}; policy {p}')


def require_safe_after_dashboard_restart(env, ev, label, count=3, spacing=2.0):
    """d28.require_safe, with ONE documented difference, used after the dashboard restarted (A3) and for every later
    action while that dashboard process has never published a drive command:
    the dashboard creates its 'web_drive' item only when it first publishes a drive command (publish() -> 'STOP' or
    a speed), so a fresh dashboard has NO item. Absent means "no dashboard drive command since start" (drive_active
    starts False), which is at least as safe as 'STOP'. A3 attempt 1 (2026-10-29) failed only on this. A PRESENT
    value other than 'STOP' still fails; every other predicate, the encoder-stillness and packet checks are unchanged."""
    snaps = []
    for i in range(count):
        if i:
            env.sleep(spacing)
        s = d28.safety_snapshot(env)
        if s['predicates'].get('web_drive_stop') is False and s['raw'].get('web_drive') in ({}, None):
            s['predicates']['web_drive_stop'] = True
            s['web_drive_absent_after_dashboard_restart'] = True
            s['ok'] = all(s['predicates'].values())
        ev.save(f'safety-{label}-{i}', s)
        snaps.append(s)
        if not s['ok']:
            raise Fail(f'{label}: safety predicate(s) failed: {[k for k, v in s["predicates"].items() if not v]}')
    if any(s['encoders'] != snaps[0]['encoders'] for s in snaps):
        raise Fail(f'{label}: encoder counts changed (motion) {[s["encoders"] for s in snaps]}')
    pk = [s['packets'] for s in snaps]
    if not all(type(p) is int for p in pk) or any(b <= a for a, b in zip(pk, pk[1:])):
        raise Fail(f'{label}: serial packet counter not progressing {pk}')
    absent = sum(1 for s in snaps if s.get('web_drive_absent_after_dashboard_restart'))
    ev.log(f'{label}: safety OK x{count}; encoders {snaps[0]["encoders"]}; packets {pk}'
           + (f'; web_drive absent in {absent}/{count} (fresh dashboard, no drive command since start)' if absent else ''))
    return snaps


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
        if step == 'features':
            before = dict(before, features={u: d28.unit_state(env, u + '.service').get('ActiveState') for u in MANAGED_FEATURES})
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
                d28.ObserverRecorder(env, base_pid, sink=ev.stream(f'observer-{step}')) as obs, \
                mux_lease(env, ev, f'stage29 {step} authorised restart', active=(step in LEASED_STEPS)):
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
        (require_safe_after_dashboard_restart if STEPS.index(step) >= STEPS.index('web') else d28.require_safe)(env, ev, f'{step}-post', count=3)
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
        elif step == 'features' and restart:
            # stop while the NEW file is on disk and the lease is valid (its restore-all is skipped), then restore the
            # old file and start it. The old code fails open at start, so a rollback starts the features once.
            with mux_lease(env, ev, 'stage29 rollback features authorised restart'):
                env.systemctl('stop', unit, timeout=60, check=False)
                restore(env, ev, bkdir, meta)
                env.systemctl('start', unit, timeout=60)
                d28.require_running(env, unit)
        else:
            restore(env, ev, bkdir, meta)
            if restart:
                d28.wait_quiescent(env, unit)
                with mux_lease(env, ev, f'stage29 rollback {step} mux restart', active=(step == 'mux')):
                    env.systemctl('restart', unit, timeout=60)
                    d28.require_running(env, unit)
                    env.sleep(min(env.steady_s, 20))
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
    if args.step == RESET_STEP:
        rollback_reset(env, ev, src / 'backup', meta, restart=True)
    else:
        rollback_files(env, ev, args.step, src / 'backup', meta, restart=True)
    ev.save('result', {'result': 'ROLLED_BACK', 'step': args.step, 'from': str(src)}); ev.seal()
    return 0


# ------------------------------------------------------------------ commissioning (lifted-wheel test only)
COMMISSION_CAPS = {'max_linear_mps': 0.05, 'max_angular_radps': 0.20, 'max_accel_mps2': 0.5}
GATE_DROPIN = '90-atlas-flysky-gate.conf'
GATE_TEXT = ('# ATLAS Stage 29 lifted-wheel commissioning ONLY. Runtime (tmpfs): removed by gate-off, gone after reboot.\n'
             '[Service]\nEnvironment=ATLAS_FLYSKY_DRIVE_ENABLED=1\n')


def gate_paths(env):
    root = Path(f'/run/user/{os.getuid()}/systemd/user') if not hasattr(env, 'runtime_unit_dir') else env.runtime_unit_dir
    return [root / f'{UNITS[k]}.d' / GATE_DROPIN for k in ('mux', 'teleop')]


def config_path(env):
    return env.project / 'config/atlas_flysky_drive.json'


def review_config(env, args):
    """Owner action: write the reviewed commissioning config (reviewed_by_owner true + caps), with a backup."""
    ev = Evidence(env, 'review-config')
    import atlas_flysky_drive_core as dcore
    p = config_path(env)
    cur = json.loads(p.read_text())
    new = dict(cur, reviewed_by_owner=True, **COMMISSION_CAPS)
    errs = dcore.validate(new)
    if errs:
        ev.log(f'REFUSED: reviewed config invalid: {errs}'); ev.seal(); return 3
    (ev.dir / 'backup').mkdir()
    shutil.copy2(p, ev.dir / 'backup' / p.name)
    d28.install_atomic((json.dumps(new, indent=2) + '\n').encode(), p, stat.S_IMODE(os.stat(p).st_mode))
    ev.log('config reviewed by owner; changed: ' + json.dumps({k: (cur.get(k), new[k]) for k in new if cur.get(k) != new[k]}))
    ev.log('takes effect only when the teleop restarts (gate-on); the running teleop keeps its loaded config')
    ev.save('result', {'result': 'REVIEWED', 'config_sha256': d28.sha(p)}); ev.seal()
    return 0


def gate_on(env, args):
    ev = Evidence(env, 'gate-on')
    import atlas_flysky_drive_core as dcore
    try:
        for step in REQUIRED_STEPS:      # the config is validated below instead: review-config changes it on purpose
            if not step_done(env, step, ignore=('config/atlas_flysky_drive.json',)):
                raise Fail(f'step {step} is not installed')
        if not step_done(env, 'features'):
            raise Fail('step features (lease-aware feature manager) is not installed: the gate-on mux restart would '
                       'start five AI/fusion services (gate-on attempts 1-2)')
        if any(g.exists() for g in gate_paths(env)):
            raise Fail('gate drop-in already present')
        require_gate_off(env, ev)
        cfg = json.loads(config_path(env).read_text())
        ok, errs = dcore.usable(cfg)
        if not ok:
            raise Fail(f'config not usable: {errs}')
        over = {k: cfg[k] for k, cap in COMMISSION_CAPS.items() if cfg[k] > cap}
        if over:
            raise Fail(f'config above the commissioning caps {COMMISSION_CAPS}: {over}')
        require_latched(env)
        p = policy(env)
        if p.get('manual_controller') != 'XBOX':
            raise Fail(f'controller is {p.get("manual_controller")}, required XBOX before gate-on')
        require_safe_after_dashboard_restart(env, ev, 'gate-on-pre', count=3)   # fresh dashboard since A3
        d28.resources_strict(env, ev, 'gate-on-preflight', env.preflight_s)
        base_pid = int(d28.unit_state(env, 'rover-base-telemetry.service').get('MainPID', '0'))
    except Fail as exc:
        ev.log(f'REFUSED, nothing changed: {exc}'); ev.save('result', {'result': 'REFUSED_NO_CHANGE', 'reason': str(exc)}); ev.seal()
        return 3
    written = []
    try:
        with d28.CpuRecorder(env, sink=ev.stream('cpu-gate-on')) as rec, \
                d28.ObserverRecorder(env, base_pid, sink=ev.stream('observer-gate-on')) as obs, \
                mux_lease(env, ev, 'stage29 gate-on mux restart'):
            env.sleep(2.5)
            d28.require_pre_window_ok(env, ev, 'gate-on', rec, obs)
            for g in gate_paths(env):
                g.parent.mkdir(parents=True, exist_ok=True)
                d28.install_atomic(GATE_TEXT.encode(), g, 0o644)
                written.append(g)
            env.systemctl('daemon-reload', timeout=30)
            obs.exempt.update(MUX_SIGNALS)
            t0 = time.time()
            ev.log('restarting atlas-cmd-vel-mux (the teleop follows via PartOf) with the gate ON')
            env.systemctl('restart', UNITS['mux'], timeout=60)
            wait_mux_back(env, ev, obs, rec, t0, args.cpu_bound_s,
                          expect=lambda p: p.get('flysky_drive_enabled') is True, what='flysky_drive_enabled True')
            try:
                d28.resources_after_restart(env, ev, 'gate-on-post', 'transient', rec, t0, args.cpu_bound_s, obs)
            except Fail as exc:
                if classify(rec, obs, t0, args.cpu_bound_s):
                    raise
                raise CpuOverrun(str(exc)) from exc
        p = policy(env)
        if not (p.get('flysky_drive_enabled') is True and p.get('manual_controller') == 'XBOX' and p.get('stop_latched') is True):
            raise Fail(f'post gate-on policy not as required (gate true, XBOX, latched): {p}')
        t = d28.require_running(env, UNITS['teleop'])
        log = env.journal(t.get('InvocationID'))
        if 'FlySky teleop ENABLED' not in log or 'Traceback' in log:
            raise Fail('teleop did not restart ENABLED')
        smp = env.sample_topics(['/cmd_vel_flysky', '/atlas/flysky/drive_status'], seconds=3.0)
        ev.save('gate-on-topic-sample', smp)
        st = json.loads(smp['/atlas/flysky/drive_status']['last'] or '{}').get('state')
        if smp['/cmd_vel_flysky']['count'] or st != 'NOT_SELECTED':
            raise Fail(f'after gate-on with Xbox selected: {smp["/cmd_vel_flysky"]["count"]} command message(s), state {st}')
        require_safe_after_dashboard_restart(env, ev, 'gate-on-post', count=3)
        ev.log('GATE ON: FlySky driving enabled for commissioning; Xbox still selected; E-STOP latched')
        ev.save('result', {'result': 'PASS'}); ev.seal()
        return 0
    except CpuOverrun as exc:
        ev.log(f'gate-on FAILED on resources with safety intact: {exc}; HELD (no automatic restart, no rollback restart)')
        hold(env, ev, 'gate-on', None, None)
        try:                                     # read-only report for the owner's decision; changes nothing
            p = policy(env)
            ev.save('held-state', {'policy': p, 'gate_dropins': [str(g) for g in gate_paths(env) if g.exists()]})
            ev.log(f'held state: gate drop-ins present {sum(g.exists() for g in gate_paths(env))}; policy latched '
                   f'{p.get("stop_latched")}, controller {p.get("manual_controller")}, gate {p.get("flysky_drive_enabled")}')
        except Exception as rexc:
            ev.log(f'held state not readable: {rexc!r}')
        ev.log('HELD: owner decides: verify and accept, or `gate-off` to undo (one mux restart).')
        ev.save('result', {'result': 'FAIL_HELD', 'reason': str(exc)}); ev.seal()
        return 1
    except Exception as exc:
        ev.log(f'gate-on FAILED: {exc!r}; removing the gate and restarting the mux')
        try:
            remove_gate(env, ev, restart=bool(written))
            ev.save('result', {'result': 'FAIL_ROLLED_BACK', 'reason': repr(exc)})
        except Exception as rb:
            ev.save('result', {'result': 'FAIL_ROLLBACK_UNCONFIRMED', 'reason': repr(exc), 'rollback': repr(rb)})
        ev.seal()
        return 1


def remove_gate(env, ev, restart=True):
    for g in gate_paths(env) + reset_paths(env):   # the FlySky reset is meaningless without the gate: removed with it
        if g.exists():
            g.unlink()
    env.systemctl('daemon-reload', timeout=30)
    if restart:
        with d28.CpuRecorder(env, sink=ev.stream('cpu-gate-off')) as rec:
            t = time.time()
            d28.wait_quiescent(env, UNITS['mux'])
            with mux_lease(env, ev, 'stage29 gate-off mux restart'):
                env.systemctl('restart', UNITS['mux'], timeout=60)
                d28.require_running(env, UNITS['mux'])
                env.sleep(min(env.steady_s, 20))
            env.sleep(max(0, env.steady_s - 20))
            d28.record_rollback_cpu(env, ev, 'gate-off', rec, t)
    ev.log('gate drop-ins removed' + (' and mux restarted' if restart else ''))


def gate_off(env, args):
    ev = Evidence(env, 'gate-off')
    try:
        require_latched(env)
    except Fail as exc:
        ev.log(f'REFUSED: {exc}. Press Xbox B (or SwB) first.'); ev.save('result', {'result': 'REFUSED_NO_CHANGE'}); ev.seal()
        return 3
    remove_gate(env, ev, restart=True)
    deadline = time.time() + env.mux_back_timeout_s
    p = {}
    while time.time() < deadline:
        try:
            p = policy(env)
            if 'manual_controller' in p:
                break
        except Exception:
            pass
        env.sleep(0.5)
    ok = p.get('flysky_drive_enabled') is False and p.get('manual_controller') == 'XBOX' and p.get('stop_latched') is True
    ev.log(f'GATE OFF {"verified" if ok else "NOT verified"}: {p}')
    ev.save('result', {'result': 'PASS' if ok else 'FAIL', 'policy': p}); ev.seal()
    return 0 if ok else 1


# ------------------------------------------------------------------ FlySky SwD E-STOP reset (2026-10-30)
RESET_DROPIN = '91-atlas-flysky-reset.conf'
RESET_TEXT = ('# ATLAS Stage 29 FlySky SwD E-STOP reset. Runtime (tmpfs): removed by gate-off / rollback, gone after reboot.\n'
              '[Service]\nEnvironment=ATLAS_FLYSKY_RESET_ENABLED=1\n')
RESET_TOPICS = ['/cmd_vel_flysky', '/atlas/flysky/drive_status', '/atlas/flysky/reset_request']


def reset_paths(env):
    root = Path(f'/run/user/{os.getuid()}/systemd/user') if not hasattr(env, 'runtime_unit_dir') else env.runtime_unit_dir
    return [root / f'{UNITS[k]}.d' / RESET_DROPIN for k in ('mux', 'teleop')]


def reset_enabled_in(p):
    r = p.get('flysky_reset')
    return isinstance(r, dict) and r.get('enabled') is True


def reset_checks(env, ev):
    """Read-only GO/NO-GO for the reset step. Returns (files_done, plan). Raises Fail with the first NO-GO reason."""
    import atlas_flysky_drive_core as dcore
    import atlas_flysky_reset as fsr
    for st in STEPS:
        if not installed(env, st):
            raise Fail(f'step {st} is not installed')
    files_done = step_done(env, RESET_STEP)
    plan = [] if files_done else file_plan(env, RESET_STEP)       # drift / partial install -> Fail, nothing changed
    if any(r.exists() for r in reset_paths(env)):
        raise Fail('FlySky reset drop-in already present (already enabled)')
    if not all(g.exists() for g in gate_paths(env)):
        raise Fail('FlySky driving gate is OFF: run gate-on first (the reset needs the gate)')
    cfg = json.loads(config_path(env).read_text())
    ok, errs = dcore.usable(cfg)
    if not ok or not reviewed_config_ok(env):
        raise Fail(f'drive config is not exactly the owner-reviewed config: {errs}')
    over = {k: cfg[k] for k, cap in COMMISSION_CAPS.items() if cfg[k] > cap}
    if over:
        raise Fail(f'config above the commissioning caps {COMMISSION_CAPS}: {over}')
    conflict = fsr.channel_conflict(cfg)
    if conflict:
        raise Fail(f'reset channel not free: {conflict}')
    require_latched(env)
    p = policy(env)
    if not (p.get('stop_latched') is True and p.get('flysky_drive_enabled') is True):
        raise Fail(f'policy not as required (latched, gate true): {p}')
    if p.get('manual_controller') != 'XBOX':
        raise Fail(f'controller is {p.get("manual_controller")}: press SELECT XBOX on the dashboard (E-STOP latched) first')
    if reset_enabled_in(p):
        raise Fail('the running mux already reports the FlySky reset enabled')
    ev.log(f'reset checks: steps installed; reset files {"already installed (re-enable only)" if files_done else "will be installed"}; '
           f'gate ON; reviewed config; CH{fsr.RESET_CHANNEL} free; latched; XBOX selected')
    return files_done, plan


def write_reset(env, ev):
    written = []
    for r in reset_paths(env):
        r.parent.mkdir(parents=True, exist_ok=True)
        d28.install_atomic(RESET_TEXT.encode(), r, 0o644)
        written.append(r)
    env.systemctl('daemon-reload', timeout=30)
    ev.log('reset drop-ins written: ' + ', '.join(str(r) for r in written))
    return written


def verify_reset(env, ev, before, protected0):
    mux, tel = d28.require_running(env, UNITS['mux']), d28.require_running(env, UNITS['teleop'])
    for unit, s, b in ((UNITS['mux'], mux, before['mux']), (UNITS['teleop'], tel, before['teleop'])):
        if s.get('MainPID') == b.get('MainPID'):
            raise Fail(f'{unit} PID did not change ({s.get("MainPID")}): restart not effective')
    mlog, tlog = env.journal(mux.get('InvocationID')), env.journal(tel.get('InvocationID'))
    if 'Traceback' in mlog or 'Traceback' in tlog:
        raise Fail('traceback in the new mux or teleop journal')
    if 'FLYSKY' not in mlog:
        raise Fail('mux journal does not show the FLYSKY channel')
    if 'FlySky teleop ENABLED' not in tlog:
        raise Fail('teleop did not restart ENABLED')
    changed = {u: (a, d28.identities(env, [u])[u]) for u, a in protected0.items() if d28.identities(env, [u])[u] != a}
    if changed:
        raise Fail(f'protected service identity changed: {changed}')
    p = policy(env)
    if not (p.get('stop_latched') is True and p.get('manual_controller') == 'XBOX' and p.get('flysky_drive_enabled') is True
            and p.get('source') == 'STOPPED' and reset_enabled_in(p)):
        raise Fail(f'post-reset policy not as required (latched, XBOX, gate true, STOPPED, flysky_reset enabled): {p}')
    smp = env.sample_topics(RESET_TOPICS, seconds=3.0)
    ev.save('reset-topic-sample', smp)
    if smp['/cmd_vel_flysky']['count'] or smp['/atlas/flysky/reset_request']['count']:
        raise Fail(f'unexpected messages with Xbox selected: cmd {smp["/cmd_vel_flysky"]["count"]}, '
                   f'reset requests {smp["/atlas/flysky/reset_request"]["count"]}')
    try:
        st = json.loads(smp['/atlas/flysky/drive_status']['last'] or '{}')
    except (TypeError, ValueError):
        st = {}
    rs = st.get('reset') or {}
    if st.get('state') != 'NOT_SELECTED' or rs.get('enabled') is not True or rs.get('state') != 'UNAVAILABLE':
        raise Fail(f'teleop status not as required (NOT_SELECTED, reset enabled and UNAVAILABLE): {st}')
    code, html = env.get_text('/v2/flysky-drive')
    jcode, js = env.get_text('/v2/flysky-drive.js')
    if code != 200 or 'id="hReset"' not in html or jcode != 200 or 'Stage 29 FlySky reset' not in js:
        raise Fail(f'dashboard does not serve the reset card ({code}/{jcode})')
    ev.log(f'reset: verified mux pid {mux.get("MainPID")}, teleop pid {tel.get("MainPID")}; policy {p}; teleop reset {rs}')


def rollback_reset(env, ev, bkdir, meta, restart=True):
    """Remove the reset drop-ins, restore every file of the backup, and (if the mux had restarted) one leased restart."""
    with d28.CpuRecorder(env, sink=ev.stream('cpu-rollback-reset')) as rec:
        t = time.time()
        for r in reset_paths(env):
            if r.exists():
                r.unlink()
        restore(env, ev, bkdir, meta)
        env.systemctl('daemon-reload', timeout=30)
        if restart:
            d28.wait_quiescent(env, UNITS['mux'])
            with mux_lease(env, ev, 'stage29 rollback reset mux restart'):
                env.systemctl('restart', UNITS['mux'], timeout=60)
                d28.require_running(env, UNITS['mux'])
                env.sleep(min(env.steady_s, 20))
        env.sleep(env.steady_s)
        d28.record_rollback_cpu(env, ev, 'reset', rec, t)
    ev.log('ROLLBACK of reset complete (drop-ins removed' + (', files restored' if meta else '') + (', mux restarted)' if restart else ')'))


def deploy_reset(env, args):
    ev = Evidence(env, 'deploy-reset')
    ev.log(f'STAGE 29 FlySky SwD reset: bound {args.cpu_bound_s} s; gate stays ON; Xbox selected; E-STOP stays latched; '
           f'no motion is commanded and the E-STOP is never released by this deployer')
    state = {'installed': False, 'written': False, 'restarted': False}
    try:
        files_done, plan = reset_checks(env, ev)
        require_safe_after_dashboard_restart(env, ev, 'reset-pre', count=3)
        d28.resources_strict(env, ev, 'reset-preflight', env.preflight_s)
        meta = backup(env, ev, plan)
        before = {'mux': d28.unit_state(env, UNITS['mux']), 'teleop': d28.unit_state(env, UNITS['teleop'])}
        protected0 = d28.identities(env, [u for u in env.protected if u not in (UNITS['mux'], UNITS['teleop'])])
        base_pid = int(d28.unit_state(env, 'rover-base-telemetry.service').get('MainPID', '0'))
    except Fail as exc:
        ev.log(f'REFUSED, nothing changed: {exc}')
        ev.save('result', {'result': 'REFUSED_NO_CHANGE', 'reason': str(exc)}); ev.seal()
        return 3
    rec = obs = t0 = None
    try:
        with d28.CpuRecorder(env, sink=ev.stream('cpu-reset')) as rec, \
                d28.ObserverRecorder(env, base_pid, sink=ev.stream('observer-reset')) as obs, \
                mux_lease(env, ev, 'stage29 reset authorised mux restart'):
            env.sleep(2.5)
            d28.require_pre_window_ok(env, ev, 'reset', rec, obs)
            for dst, data, mode, _, _ in plan:
                dst.parent.mkdir(parents=True, exist_ok=True)
                d28.install_atomic(data, dst, mode)
            state['installed'] = bool(plan)
            ev.log('installed: ' + (', '.join(f'{dst.name}={hh[:12]}' for dst, _, _, _, hh in plan) or 'nothing (files already installed)'))
            write_reset(env, ev)
            state['written'] = True
            obs.exempt.update(MUX_SIGNALS)
            t0 = time.time()
            ev.log('restarting atlas-cmd-vel-mux ONLY (the teleop follows via PartOf) with the FlySky reset enabled')
            env.systemctl('restart', UNITS['mux'], timeout=60)
            state['restarted'] = True
            wait_mux_back(env, ev, obs, rec, t0, args.cpu_bound_s,
                          expect=lambda p: reset_enabled_in(p) and p.get('flysky_drive_enabled') is True,
                          what='flysky_reset enabled')
            try:
                d28.resources_after_restart(env, ev, 'reset-post', 'transient', rec, t0, args.cpu_bound_s, obs)
            except Fail as exc:
                if classify(rec, obs, t0, args.cpu_bound_s):
                    raise
                raise CpuOverrun(str(exc)) from exc
            recovery_mean(ev, 'reset', rec, t0, args.cpu_bound_s)
            ev.save('cpu-recorder-reset', {'t_restart': t0, 'samples': rec.samples, 'ram_temp': rec.rt})
        verify_reset(env, ev, before, protected0)
        require_safe_after_dashboard_restart(env, ev, 'reset-post', count=3)
        ev.log('RESET STEP PASS: FlySky SwD reset enabled; Xbox selected; E-STOP latched; nothing moved')
        ev.save('result', {'result': 'PASS', 'step': RESET_STEP, 'files_installed': state['installed']}); ev.seal()
        return 0
    except CpuOverrun as exc:
        ev.log(f'RESET STEP FAILED on resources with safety intact: {exc}')
        hold(env, ev, RESET_STEP, rec, t0)
        ev.log(f'HELD: no automatic restart. Rollback on owner decision: rollback --step reset --evidence {ev.dir}')
        ev.save('result', {'result': 'FAIL_HELD', 'step': RESET_STEP, 'reason': str(exc), 'rollback_evidence': str(ev.dir)}); ev.seal()
        return 1
    except Exception as exc:
        if not (state['installed'] or state['written']):
            ev.log(f'REFUSED before any change: {exc!r}')
            ev.save('result', {'result': 'REFUSED_NO_CHANGE', 'step': RESET_STEP, 'reason': repr(exc)}); ev.seal()
            return 3
        ev.log(f'RESET STEP FAILED (safety/verification): {exc!r}; rolling back')
        try:
            rollback_reset(env, ev, ev.dir / 'backup', meta, restart=state['restarted'])
            ev.save('result', {'result': 'FAIL_ROLLED_BACK', 'step': RESET_STEP, 'reason': repr(exc)})
        except Exception as rb:
            ev.log(f'ROLLBACK NOT CONFIRMED ({rb!r}): owner inspection required; no further restart attempted')
            ev.save('result', {'result': 'FAIL_ROLLBACK_UNCONFIRMED', 'step': RESET_STEP, 'reason': repr(exc), 'rollback': repr(rb)})
        ev.seal()
        return 1


def preflight_reset(env, args):
    """Read-only GO/NO-GO for `deploy --step reset` (the Stage A preflight requires the gate OFF, this one ON)."""
    ev = Evidence(env, 'preflight-reset')
    ok = True
    for label, fn in (('reset', lambda: reset_checks(env, ev)),
                      ('safety', lambda: require_safe_after_dashboard_restart(env, ev, 'preflight-reset')),
                      ('resources', lambda: d28.resources_strict(env, ev, 'preflight-reset', env.preflight_s))):
        try:
            fn()
        except Exception as exc:
            ok = False
            ev.log(f'{label}: NO-GO: {exc}')
    ev.log('PREFLIGHT RESET ' + ('GO' if ok else 'NO-GO'))
    ev.save('result', {'result': 'GO' if ok else 'NO-GO'}); ev.seal()
    return 0 if ok else 1


def require_latched(env):
    if env.get('/api/estop/state').get('latched') is not True:
        raise Fail('E-STOP not latched')


CONFIG_REL = 'config/atlas_flysky_drive.json'


def reviewed_config_ok(env):
    """The live config is EXACTLY what review-config writes from the reviewed candidate: candidate +
    reviewed_by_owner true + COMMISSION_CAPS, nothing else (found at gate-on attempt 2: preflight rejected it)."""
    spec = MANIFEST['steps']['teleop']['files'][CONFIG_REL]
    src = REPO / spec['source']
    if d28.sha(src) != spec['candidate_sha256']:
        return False
    try:
        live = json.loads(config_path(env).read_text())
    except (OSError, ValueError):
        return False
    return live == dict(json.loads(src.read_text()), reviewed_by_owner=True, **COMMISSION_CAPS)


def preflight(env, args):
    ev = Evidence(env, 'preflight')
    ok = True
    reviewed = reviewed_config_ok(env)
    if step_done(env, RESET_STEP):
        ev.log('step reset: files INSTALLED (FlySky SwD reset ' + ('ENABLED' if all(r.exists() for r in reset_paths(env)) else 'not enabled') + ')')
    for step in STEPS:
        try:
            if step_done(env, step, ignore=(CONFIG_REL,) if reviewed else ()):
                ev.log(f'step {step}: INSTALLED' + (' (config: the owner-reviewed commissioning config)'
                                                     if reviewed and CONFIG_REL in MANIFEST['steps'][step]['files'] else ''))
            elif MANIFEST['steps'][step].get('supersedes') and not step_done(env, MANIFEST['steps'][step]['supersedes']):
                ev.log(f'step {step}: builds on step {MANIFEST["steps"][step]["supersedes"]}, not installed yet; checked after it')
            else:
                file_plan(env, step)
                ev.log(f'step {step}: candidates rebuilt from live files, all hashes match')
        except Fail as exc:
            ok = False
            ev.log(f'step {step}: {exc}')
    for label, fn in (('gate', lambda: require_gate_off(env, ev)),
                      ('estop', lambda: require_latched(env)),
                      ('safety', lambda: require_safe_after_dashboard_restart(env, ev, 'preflight')),   # dashboard runs since A3
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
    p.add_argument('action', choices=['preflight', 'deploy', 'rollback', 'review-config', 'gate-on', 'gate-off'])
    p.add_argument('--step', choices=ALL_STEPS)
    p.add_argument('--cpu-bound-s', type=float, help='owner-approved transient bound for THIS step (no default)')
    p.add_argument('--evidence', help='rollback: the evidence directory of the step being undone')
    p.add_argument('--owner-confirms-estop-latched', action='store_true')
    p.add_argument('--owner-confirms-rover-lifted-and-clear', action='store_true')
    p.add_argument('--evidence-root')
    p.add_argument('--owner-reviewed-config', action='store_true')
    a = p.parse_args(argv)
    env = env or Env(**({'evidence_root': Path(a.evidence_root)} if a.evidence_root else {}))
    if a.action == 'preflight':
        return preflight_reset(env, a) if a.step == RESET_STEP else preflight(env, a)
    if os.environ.get('OWNER_APPROVED') != 'yes':
        print('refused: OWNER_APPROVED=yes required (separate owner approval)'); return 2
    if a.action == 'review-config':
        if not a.owner_reviewed_config:
            print('refused: --owner-reviewed-config required'); return 2
        return review_config(env, a)
    if not (a.owner_confirms_estop_latched and a.owner_confirms_rover_lifted_and_clear):
        print('refused: both owner confirmations are required'); return 2
    if a.action == 'gate-off':
        return gate_off(env, a)
    if a.action == 'gate-on':
        if a.cpu_bound_s is None or not 0 < a.cpu_bound_s <= MAX_BOUND_S:
            print(f'refused: --cpu-bound-s must be given explicitly, 0 < bound <= {MAX_BOUND_S}'); return 2
        return gate_on(env, a)
    if not a.step:
        print('refused: --step is required'); return 2
    if a.action == 'rollback':
        if not a.evidence:
            print('refused: --evidence required'); return 2
        return rollback(env, a)
    if a.cpu_bound_s is None or not 0 < a.cpu_bound_s <= MAX_BOUND_S:
        print(f'refused: --cpu-bound-s must be given explicitly, 0 < bound <= {MAX_BOUND_S}'); return 2
    if a.step == RESET_STEP:
        return deploy_reset(env, a)
    return deploy_step(env, a)


if __name__ == '__main__':
    sys.exit(main())
