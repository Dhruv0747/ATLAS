#!/usr/bin/env python3
"""ATLAS parked camera profile: pause Nav2 NAVIGATION (not localization) around ONE stationary Vision Lab session.

Why: on 21 Oct the only camera session that passed the unchanged 75% CPU guard ran while Nav2's navigation servers
were inactive; with them active the parked Jetson sits ~5 points higher (docs/ATLAS_CPU_BASELINE_SHIFT_NAV2_20261024.md).
This tool reproduces that state on purpose, briefly, and puts it back.

What it does (and nothing else):
  * PAUSE  -> /lifecycle_manager_navigation/manage_nodes command PAUSE (1): Nav2 marks the system inactive, stops its
             bond watchdog, then deactivates controller/planner/behavior/bt_navigator/waypoint_follower.
             map_server + AMCL (/lifecycle_manager_localization) are never touched.
  * RESUME -> command RESUME (2) and verify /lifecycle_manager_navigation/is_active == true.
  It never restarts or stops a systemd service, never changes parameters, guards, E-STOP, motors or maps, and never
  starts the camera (the owner presses Start in the Vision Lab).

Safety design:
  * pause refuses unless: E-STOP latched, manual-only, commissioning disarmed, policy source STOPPED, commands zero,
    mission READY, AMCL fresh, navigation active, localization active, no Astra/Vision Lab process, no pause marker.
  * BEFORE sending PAUSE a systemd user timer is armed that runs `resume` after --max-pause-s (default 600 s) even if
    this process dies. `resume` is idempotent.
  * ROS is joined only by a short-lived client subprocess (FASTDDS_BUILTIN_TRANSPORTS=UDPv4, like atlas-localization)
    for pause / resume / status. `session` never holds a ROS participant while the camera may run: it watches only
    /proc/stat and the Vision Lab state file (tmpfs), so it adds no discovery or dashboard load to the session.
  * Resume failure is reported (RESUME_INCOMPLETE) and left for the owner; no automatic service restart.

usage (Jetson; every command except status/check needs OWNER_APPROVED=yes):
  atlas_parked_camera_profile.py check            read-only preconditions + Nav2 state
  atlas_parked_camera_profile.py status           read-only Nav2/localization lifecycle state
  atlas_parked_camera_profile.py pause            arm watchdog, pause navigation, verify
  atlas_parked_camera_profile.py resume           resume navigation (idempotent), verify, disarm watchdog
  atlas_parked_camera_profile.py session          pause -> settle -> wait for ONE Vision Lab session -> resume
  (internal) atlas_parked_camera_profile.py ros <status|pause|resume>
"""
import argparse, json, math, os, subprocess, sys, time
from pathlib import Path

NAV_MGR = '/lifecycle_manager_navigation'
LOC_MGR = '/lifecycle_manager_localization'
NAV_NODES = ('controller_server', 'planner_server', 'behavior_server', 'bt_navigator', 'waypoint_follower')
LOC_NODES = ('map_server', 'amcl')
PAUSE, RESUME = 1, 2
DASH = os.environ.get('ATLAS_DASHBOARD_URL', 'http://127.0.0.1:8088')
RUN = Path(os.environ.get('XDG_RUNTIME_DIR') or '/run/user/%d' % os.getuid())
MARKER = Path(os.environ.get('ATLAS_PARKED_MARKER') or RUN / 'atlas-parked-camera-profile.json')
VISION_STATE = Path(os.environ.get('ATLAS_VISION3D_STATE_PATH') or RUN / 'atlas-vision3d-viewer.json')
WATCHDOG_UNIT = 'atlas-parked-camera-resume'
SELF = Path(__file__).resolve()
TERMINAL = ('OFF', 'RESOURCE BLOCKED', 'FAILED', 'SENSOR ERROR', 'STOPPED')
# Optional (--with-ai-pause, owner-approved 24 Oct 14:56): non-essential perception/assistant features that may be
# stopped for the parked camera session and are restarted (staggered, verified) BEFORE navigation resumes.
# Checked against the live sources: no Requires/BindsTo/PartOf from any other unit; not watched by sensor recovery;
# their topics feed only the Dashboard display, voice chatter and an INFO 'ai_camera' field in safety status, plus
# /camera/semantic_obstacles into Nav2 costmaps (no expected_update_rate; navigation is paused meanwhile).
# Deliberately NOT included: voice companion, local LLM (offline fallback), agent supervisor, every safety, motion,
# sensor, localization and camera service. The list is fixed here and cannot be extended from the command line.
AI_SERVICES = ('atlas-ai-annotator', 'atlas-agent-team', 'atlas-person-sensor-fusion', 'atlas-follow-person',
               'atlas-camera-tracker', 'atlas-experience-store', 'atlas-active-vision', 'atlas-vision-lidar-fusion',
               'atlas-visual-cloud-agent', 'atlas-visual-cloud-server')
SYSTEMCTL = os.environ.get('ATLAS_SYSTEMCTL', 'systemctl')      # offline tests substitute a fake


class Refuse(RuntimeError):
    pass


def log(event, **kw):
    row = dict(t=round(time.time(), 3), event=event, **kw)
    print(json.dumps(row, default=str), flush=True)
    return row


# ---------------------------------------------------------------- ROS client (short-lived subprocess only)
def ros_main(action, timeout_s):
    import rclpy
    from lifecycle_msgs.srv import GetState
    from nav2_msgs.srv import ManageLifecycleNodes
    from std_srvs.srv import Trigger
    rclpy.init()
    node = rclpy.create_node('atlas_parked_camera_profile_%d' % os.getpid())

    def call(srv_type, name, request, timeout):
        cli = node.create_client(srv_type, name)
        try:
            if not cli.wait_for_service(timeout_sec=min(10.0, timeout)):
                return None
            fut = cli.call_async(request); end = time.monotonic() + timeout
            while not fut.done() and time.monotonic() < end:
                rclpy.spin_once(node, timeout_sec=0.1)
            return fut.result() if fut.done() else None
        finally:
            node.destroy_client(cli)

    def active(mgr):
        r = call(Trigger, mgr + '/is_active', Trigger.Request(), 10.0)
        return None if r is None else bool(r.success)

    def states(names):
        # A fresh participant on the busy Jetson can need several seconds to discover each service (24 Oct: one
        # get_state unanswered within 5 s, all answered on the next run). Retry unanswered nodes; never guess.
        out = {n: None for n in names}
        for _ in range(3):
            for n in [k for k, v in out.items() if v is None]:
                r = call(GetState, '/%s/get_state' % n, GetState.Request(), 10.0)
                out[n] = None if r is None else r.current_state.label
            if all(v is not None for v in out.values()):
                break
        return out

    out = {'action': action}
    try:
        if action in ('pause', 'resume'):
            req = ManageLifecycleNodes.Request(); req.command = PAUSE if action == 'pause' else RESUME
            r = call(ManageLifecycleNodes, NAV_MGR + '/manage_nodes', req, timeout_s)
            out['manage_success'] = None if r is None else bool(r.success)
        out.update(nav_active=active(NAV_MGR), loc_active=active(LOC_MGR), nav_states=states(NAV_NODES), loc_states=states(LOC_NODES))
    finally:
        node.destroy_node(); rclpy.shutdown()
    print('ROSRESULT ' + json.dumps(out), flush=True)


def ros(action, timeout_s=30.0):
    env = dict(os.environ); env.setdefault('FASTDDS_BUILTIN_TRANSPORTS', 'UDPv4')
    r = subprocess.run([sys.executable, str(SELF), 'ros', action, '--timeout', str(timeout_s)], env=env,
                       capture_output=True, text=True, timeout=timeout_s + 60)
    line = [l for l in r.stdout.splitlines() if l.startswith('ROSRESULT ')]
    if not line:
        raise RuntimeError('ROS client failed (rc %s): %s' % (r.returncode, r.stderr.strip()[-400:]))
    return json.loads(line[0][10:])


# ---------------------------------------------------------------- read-only preconditions (no ROS participant)
def http_json(path, timeout=5):
    import urllib.request
    return json.load(urllib.request.urlopen(DASH + path, timeout=timeout))


def astra_running():
    me = {os.getpid(), os.getppid()}
    for d in os.listdir('/proc'):
        if d.isdigit() and int(d) not in me:
            try:
                c = Path('/proc/%s/cmdline' % d).read_bytes()
            except OSError:
                continue
            if b'astra_camera_node' in c or b'atlas_vision3d_runtime.py\x00--worker' in c or b'atlas_vision3d_cloud_node.py' in c:
                return True
    return False


def parked_checks():
    """Returns evidence dict; raises Refuse with the first failed condition."""
    st = http_json('/api/status'); r = st.get('ros', {})
    def fresh(key, limit=2.0):
        v = r.get(key) or {}
        if not isinstance(v.get('age'), (int, float)) or not 0 <= v['age'] <= limit:
            raise Refuse('stale or missing ' + key)
        return v['value']
    p = fresh('control_policy'); p = json.loads(p) if isinstance(p, str) else p
    if not (p.get('stop_latched') is True and p.get('manual_only') is True and p.get('commission_armed') is False and p.get('source') == 'STOPPED'):
        raise Refuse('robot is not parked: policy %s' % {k: p.get(k) for k in ('stop_latched', 'manual_only', 'commission_armed', 'source')})
    cmd = fresh('cmd_vel')
    if any(not math.isfinite(float(cmd.get(k, float('nan')))) or float(cmd[k]) != 0 for k in ('lin', 'ang')):
        raise Refuse('nonzero/unknown motor command')
    if fresh('mission_status') != 'READY':
        raise Refuse('mission is not READY')
    if float(fresh('motor_speed')) != 0:
        raise Refuse('measured motor speed nonzero')
    fresh('amcl_quality', 5.0)   # localization alive, so RESUME can find map->base_link for the costmaps
    est = http_json('/api/estop/state')
    if est.get('latched') is not True:
        raise Refuse('E-STOP not latched')
    if astra_running():
        raise Refuse('an Astra/Vision Lab camera process is running')
    return {'policy_source': p.get('source'), 'mission': 'READY', 'estop_latched': True, 'commands_zero': True}


def cpu_ticks():
    v = list(map(int, Path('/proc/stat').read_text().splitlines()[0].split()[1:]))
    return sum(v), v[3] + v[4]


def wait_settled(limit=75.0, need=5, max_s=90.0):
    a = cpu_ticks(); run = 0; samples = []; end = time.monotonic() + max_s
    while time.monotonic() < end:
        time.sleep(1.0); b = cpu_ticks()
        busy = 100.0 * (1 - (b[1] - a[1]) / max(1, b[0] - a[0])); a = b; samples.append(round(busy, 1))
        run = run + 1 if busy <= limit else 0
        if run >= need:
            return True, samples
    return False, samples


# ---------------------------------------------------------------- watchdog (guaranteed resume)
def arm_watchdog(seconds):
    if os.environ.get('ATLAS_PARKED_TEST_WATCHDOG'):   # offline tests only: detached sleeper instead of systemd
        p = subprocess.Popen(['bash', '-c', 'sleep %d; OWNER_APPROVED=yes "%s" "%s" resume --reason watchdog' % (seconds, sys.executable, SELF)],
                             start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=dict(os.environ))
        return {'kind': 'test-sleeper', 'pid': p.pid, 'seconds': seconds}
    subprocess.run(['systemctl', '--user', 'stop', WATCHDOG_UNIT + '.timer', WATCHDOG_UNIT + '.service'], capture_output=True)
    cmd = ['systemd-run', '--user', '--unit=' + WATCHDOG_UNIT, '--on-active=%ds' % seconds, '--timer-property=AccuracySec=1s',
           '--setenv=OWNER_APPROVED=yes', '--setenv=FASTDDS_BUILTIN_TRANSPORTS=UDPv4', '/bin/bash', '-lc',
           'source /opt/ros/humble/setup.bash; exec /usr/bin/python3 %s resume --reason watchdog' % SELF]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise Refuse('could not arm the resume watchdog: ' + r.stderr.strip()[-300:])
    return {'kind': 'systemd-timer', 'unit': WATCHDOG_UNIT, 'seconds': seconds}


def disarm_watchdog(info):
    # When this IS the watchdog's resume, never stop/kill the watchdog itself (it would kill this process).
    if not info or os.environ.get('ATLAS_PARKED_FROM_WATCHDOG') == '1':
        return
    if info.get('kind') == 'test-sleeper':
        try:
            os.killpg(info['pid'], 15)
        except OSError:
            pass
    elif info.get('kind') == 'systemd-timer':
        subprocess.run(['systemctl', '--user', 'stop', WATCHDOG_UNIT + '.timer'], capture_output=True)


# ---------------------------------------------------------------- optional AI-feature pause
def unit_state(u):
    r = subprocess.run([SYSTEMCTL, '--user', 'is-active', u + '.service'], capture_output=True, text=True)
    return r.stdout.strip() or 'unknown'


def stop_ai_services():
    stopped, skipped = [], {}
    for u in AI_SERVICES:
        st = unit_state(u)
        if st != 'active':
            skipped[u] = st; continue                    # only stop what is running; never start what was off
        subprocess.run([SYSTEMCTL, '--user', 'stop', u + '.service'], capture_output=True, text=True, timeout=30)
        stopped.append(u)
    after = {u: unit_state(u) for u in stopped}
    return stopped, skipped, after


def start_ai_services(units, stagger_s=3.0, verify_s=30.0):
    for u in units:                                      # staggered: each start joins the ROS graph (CPU spike)
        subprocess.run([SYSTEMCTL, '--user', 'start', u + '.service'], capture_output=True, text=True, timeout=60)
        time.sleep(stagger_s)
    end = time.monotonic() + verify_s; st = {}
    while time.monotonic() < end:
        st = {u: unit_state(u) for u in units}
        if all(v == 'active' for v in st.values()):
            break
        time.sleep(2.0)
    return st


# ---------------------------------------------------------------- commands
def require_approval():
    if os.environ.get('OWNER_APPROVED') != 'yes':
        raise Refuse('owner approval required (OWNER_APPROVED=yes)')


def cmd_pause(max_pause_s, with_ai=False):
    require_approval()
    if MARKER.exists():
        raise Refuse('a parked profile is already recorded (%s); run resume first' % MARKER)
    ev = parked_checks()
    s = ros('status')
    if s['nav_active'] is not True or s['loc_active'] is not True:
        raise Refuse('Nav2 not in the expected state before pause: %s' % s)
    wd = arm_watchdog(max_pause_s)                      # armed BEFORE anything is paused
    MARKER.write_text(json.dumps({'paused_at': time.time(), 'watchdog': wd, 'max_pause_s': max_pause_s, 'before': s}))
    r = ros('pause', 30.0)
    ok = r.get('manage_success') is True and r.get('nav_active') is False and r.get('loc_active') is True and \
        all(v == 'inactive' for v in r['nav_states'].values()) and all(v == 'active' for v in r['loc_states'].values())
    log('pause', ok=ok, evidence=ev, ros=r, watchdog=wd)
    if not ok:
        log('pause_incomplete_resuming'); cmd_resume('pause verification failed')
        raise Refuse('pause did not reach the expected state; resume attempted')
    if with_ai:
        info = json.loads(MARKER.read_text()); info['ai_services_stopped'] = []
        MARKER.write_text(json.dumps(info))             # record intent before stopping anything
        stopped, skipped, after = stop_ai_services()
        info['ai_services_stopped'] = stopped; MARKER.write_text(json.dumps(info))
        ok_ai = all(v != 'active' for v in after.values())
        log('ai_pause', ok=ok_ai, stopped=stopped, not_running_before=skipped, state_after=after)
        if not ok_ai:
            log('ai_pause_incomplete_resuming'); cmd_resume('AI pause verification failed')
            raise Refuse('AI services did not stop as expected; everything was resumed')
    time.sleep(3.0)
    parked_checks()                                     # mission still READY, commands zero, AMCL alive
    return r


def cmd_resume(reason='manual', timeout_s=120.0):
    require_approval()
    info = json.loads(MARKER.read_text()) if MARKER.exists() else {}
    units = info.get('ai_services_stopped') or []
    if units:                                            # features back first, so semantic obstacles exist on resume
        st = start_ai_services(units)
        ok_ai = all(v == 'active' for v in st.values())
        log('ai_resume', ok=ok_ai, state=st)
        if not ok_ai:
            log('AI_RESUME_INCOMPLETE', note='some AI feature services did not come back; navigation resume continues; no repeated restarts', state=st)
        info['ai_services_stopped'] = [u for u, v in st.items() if v != 'active']
        if MARKER.exists():
            MARKER.write_text(json.dumps(info))
    s = ros('status')
    if s['nav_active'] is True and all(v == 'active' for v in s['nav_states'].values()):
        log('resume', ok=True, already_active=True, reason=reason, ros=s)
    else:
        r = ros('resume', timeout_s)
        end = time.monotonic() + timeout_s
        while r.get('nav_active') is not True and time.monotonic() < end:
            time.sleep(3.0); r = ros('status')
        ok = r.get('nav_active') is True and all(v == 'active' for v in r['nav_states'].values()) and r.get('loc_active') is True
        log('resume', ok=ok, reason=reason, ros=r)
        if not ok:
            log('RESUME_INCOMPLETE', note='navigation left paused (no autonomy possible); no service restart performed; owner decision required')
            return False
    try:
        MARKER.unlink()                                  # clear the record first, then disarm the watchdog
    except FileNotFoundError:
        pass
    disarm_watchdog(info.get('watchdog'))
    return True


def vision_state():
    try:
        return json.loads(VISION_STATE.read_text())
    except (OSError, ValueError):
        return {}


def cmd_session(max_pause_s, wait_start_s, with_ai=False):
    require_approval()
    before = vision_state().get('worker_pid')
    cmd_pause(max_pause_s, with_ai)
    try:
        settled, samples = wait_settled()
        log('settle', settled=settled, cpu_samples=samples)
        log('READY_FOR_CAMERA', note='press Start ONCE in the Vision Lab now (Depth); this tool will resume Nav2 when the session ends',
            wait_start_s=wait_start_s)
        end = time.monotonic() + wait_start_s; seen = None; last = None
        while time.monotonic() < end:
            st = vision_state(); pid = st.get('worker_pid'); state = st.get('state')
            if pid and pid != before:
                if seen is None:
                    seen = pid; log('camera_session_started', worker_pid=pid, state=state); end = time.monotonic() + 120
                if state in TERMINAL and pid == seen:
                    log('camera_session_ended', worker_pid=pid, state=state, reason=st.get('reason'), samples=st.get('sample_count'))
                    break
            if state != last:
                last = state
            time.sleep(1.0)
        else:
            log('camera_wait_window_elapsed', session_seen=bool(seen))
        time.sleep(3.0 if seen else 0)
    finally:
        ok = cmd_resume('session end')
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=('check', 'status', 'pause', 'resume', 'session', 'ros'))
    ap.add_argument('action', nargs='?')
    ap.add_argument('--timeout', type=float, default=30.0)
    ap.add_argument('--max-pause-s', type=int, default=600)
    ap.add_argument('--wait-start-s', type=int, default=300)
    ap.add_argument('--reason', default='manual')
    ap.add_argument('--with-ai-pause', action='store_true', help='also stop the fixed AI_SERVICES list (restarted on resume)')
    a = ap.parse_args()
    if a.reason == 'watchdog':
        os.environ['ATLAS_PARKED_FROM_WATCHDOG'] = '1'
    try:
        if a.cmd == 'ros':
            ros_main(a.action, a.timeout)
        elif a.cmd == 'status':
            log('status', ros=ros('status'), marker=MARKER.exists())
        elif a.cmd == 'check':
            ev = parked_checks(); s = ros('status')
            log('check', ok=s['nav_active'] is True and s['loc_active'] is True, evidence=ev, ros=s, marker=MARKER.exists(),
                ai_services={u: unit_state(u) for u in AI_SERVICES})
        elif a.cmd == 'pause':
            cmd_pause(a.max_pause_s, a.with_ai_pause)
        elif a.cmd == 'resume':
            sys.exit(0 if cmd_resume(a.reason) else 3)
        elif a.cmd == 'session':
            sys.exit(0 if cmd_session(a.max_pause_s, a.wait_start_s, a.with_ai_pause) else 3)
    except Refuse as e:
        log('REFUSE', reason=str(e)); sys.exit(2)


if __name__ == '__main__':
    main()
