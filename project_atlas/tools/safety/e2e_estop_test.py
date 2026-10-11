#!/usr/bin/env python3
"""Isolated end-to-end E-STOP test: real rover-status-web + real cmd_vel mux + synthetic remote.

Runs ONLY on a private DDS domain with ROS_LOCALHOST_ONLY=1, so no motor driver, base node or other
ATLAS process can see any message. The web server listens on 127.0.0.1:<port>. The shutdown and
reboot actions are never called. Writes a JSON evidence file and exits non-zero on any failure.

Usage: e2e_estop_test.py <scripts_dir> <out.json> [--reset]
  scripts_dir  a COPY of the Jetson scripts with the stage(s) under test installed
"""
import json, os, signal, socket, subprocess, sys, threading, time, urllib.error, urllib.request
assert os.environ.get('ROS_DOMAIN_ID') not in (None, '', '0'), 'isolated ROS domain required'
assert os.environ.get('ROS_LOCALHOST_ONLY') == '1', 'ROS_LOCALHOST_ONLY=1 required'
import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Joy
from std_msgs.msg import String

SCRIPTS, OUT = sys.argv[1], sys.argv[2]
PORT = 18088; BASE = f'http://127.0.0.1:{PORT}'
HERE = os.path.dirname(os.path.abspath(__file__))
EVID, FAIL, LOG = {}, [], []


def log(msg):
    line = f'{time.strftime("%H:%M:%S")} {msg}'; LOG.append(line); print(line, flush=True)


def check(name, cond, detail=''):
    EVID.setdefault('checks', []).append({'check': name, 'pass': bool(cond), 'detail': detail})
    log(('PASS ' if cond else 'FAIL ') + name + (f' — {detail}' if detail else ''))
    if not cond: FAIL.append(name)


class Rig:
    def __init__(self):
        rclpy.init(); self.n = rclpy.create_node('estop_e2e_rig')
        self.joy_pub = self.n.create_publisher(Joy, '/joy', 10)
        self.joy_mode, self.lock = 'neutral', threading.Lock()
        self.cmd, self.web, self.policy, self.policy_t = [], [], None, 0.0
        self.n.create_subscription(Twist, '/cmd_vel', lambda m: self.cmd.append((time.monotonic(), m.linear.x, m.angular.z)), 50)
        self.n.create_subscription(Twist, '/cmd_vel_web', lambda m: self.web.append((time.monotonic(), m.linear.x, m.angular.z)), 50)
        self.n.create_subscription(String, '/atlas/control_policy', self._policy, 10)
        self.n.create_timer(0.05, self._joy)
        self.odom_pub = self.n.create_publisher(Odometry, '/odom', 10); self.odom_vx = 0.0
        self.n.create_timer(0.1, self._odom)
        threading.Thread(target=rclpy.spin, args=(self.n,), daemon=True).start()

    def _odom(self):
        m = Odometry(); m.twist.twist.linear.x = self.odom_vx; self.odom_pub.publish(m)

    def _policy(self, m):
        try: self.policy = json.loads(m.data); self.policy_t = time.monotonic()
        except ValueError: pass

    def _joy(self):
        mode = self.joy_mode
        if mode == 'none': return
        axes, buttons = [0.0] * 8, [0] * 11
        if mode == 'B': buttons[1] = 1
        if mode == 'LB': buttons[4] = 1
        if mode == 'LB+stick': buttons[4] = 1; axes[1] = 0.5
        if mode == 'stick': axes[1] = 0.5
        m = Joy(); m.axes, m.buttons = axes, buttons; self.joy_pub.publish(m)

    def latched(self):
        return self.policy.get('stop_latched') if self.policy and time.monotonic() - self.policy_t < 1.0 else None

    def wait_latched(self, want, timeout=3.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.latched() is want: return True
            time.sleep(0.05)
        return False

    def moving_since(self, t0, src='cmd'):
        return [x for x in (self.cmd if src == 'cmd' else self.web) if x[0] >= t0 and (abs(x[1]) > 1e-4 or abs(x[2]) > 1e-4)]

    def joy(self, mode, seconds=0.0):
        self.joy_mode = mode; time.sleep(seconds)


def post(data, timeout=3.0):
    body = '&'.join(f'{k}={v}' for k, v in data.items()).encode()
    req = urllib.request.Request(BASE + '/', data=body, method='POST', headers={'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return r.status, json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read() or b'{}')
        except ValueError: return e.code, {}
    except OSError as e:
        return None, {'error': str(e)}


HDR = {'Content-Type': 'application/json', 'X-Atlas-Wifi': '1', 'Origin': f'http://127.0.0.1:{PORT}'}


def get_state():
    with urllib.request.urlopen(BASE + '/api/estop/state', timeout=3) as r: return json.loads(r.read())


def post_reset(nonce, pin, headers=HDR, confirm='RESET_ESTOP'):
    req = urllib.request.Request(BASE + '/api/estop/reset', data=json.dumps({'nonce': nonce, 'pin': pin, 'confirm': confirm}).encode(),
                                 method='POST', headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as r: return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}')


def drive(press=None, start=False, timeout=3.0):
    f = {'action': 'drive', 'linear': '.3', 'angular': '0'}
    if press: f.update(press=press, start='1' if start else '0')
    return post(f, timeout)


def start_server():
    p = subprocess.Popen([sys.executable, os.path.join(HERE, 'e2e_web_server.py'), SCRIPTS, str(PORT)],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=os.environ)
    end = time.monotonic() + 40
    while time.monotonic() < end:
        try:
            with urllib.request.urlopen(BASE + '/api/status', timeout=2) as r:
                if r.status == 200 and json.loads(r.read()).get('ros', {}).get('control_policy', {}).get('age', 99) < 2:
                    return p
        except (OSError, ValueError): pass
        time.sleep(0.5)
    raise SystemExit('web server did not become ready')


def remote_release(rig):
    """The documented physical procedure: sticks neutral, hold LB >= 2 s, let go."""
    rig.joy('neutral', 0.6); rig.joy('LB', 2.4)
    still = rig.latched()
    rig.joy('neutral', 0.4)
    return still, rig.wait_latched(False, 2.0)


def main():
    env_mux = {**os.environ, 'ATLAS_MANUAL_ONLY': '0', 'ATLAS_ULTRASONIC_ENABLED': '1'}   # as on the live unit
    mux = subprocess.Popen([sys.executable, os.path.join(SCRIPTS, 'atlas_cmd_vel_mux.py')], env=env_mux,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rig = Rig(); server = None
    try:
        time.sleep(3); server = start_server(); log('mux and web server up (isolated domain)')
        check('mux starts latched', rig.wait_latched(True, 5), str(rig.policy and rig.policy.get('stop_reason')))

        # ---- remote release procedure (existing, physical) ----
        rig.joy('neutral', 0.6); rig.joy('LB+stick', 2.5); rig.joy('neutral', 0.3)
        check('remote: LB hold with a stick deflected does NOT release', rig.latched() is True)
        rig.joy('neutral', 0.6); rig.joy('LB', 1.2); rig.joy('neutral', 0.4)
        check('remote: LB held 1.2 s (< 2 s) does NOT release', rig.latched() is True)
        held, released = remote_release(rig)
        check('remote: still latched while LB is held past 2 s', held is True)
        check('remote: neutral + LB >= 2 s + let go releases the latch', released, str(rig.policy and rig.policy.get('stop_reason')))

        # ---- normal drive works when unlatched (positive control) ----
        t0 = time.monotonic(); codes = [drive('p1', start=(i == 0))[0] for i in range(5)]
        post({'action': 'stop'}); time.sleep(0.3)
        check('unlatched: drive accepted by the server', codes == [200] * 5, str(codes))
        check('unlatched: web channel carried the drive command', bool(rig.moving_since(t0, 'web')))
        EVID['unlatched_mux_output_nonzero'] = bool(rig.moving_since(t0))   # may be 0 if mux guards block WEB in isolation

        # ---- held drive + E-STOP: latch, then nothing accepted ----
        stop_loop = threading.Event(); codes_after = []
        estop_at = [None]
        def held_button():
            first = True
            while not stop_loop.is_set():
                c, _ = drive('held1', start=first, timeout=1.5); first = False
                if estop_at[0] is not None: codes_after.append(c)
                time.sleep(0.12)
        th = threading.Thread(target=held_button); th.start(); time.sleep(0.6)
        c, p = post({'action': 'e_stop'}); estop_at[0] = time.monotonic()
        check('E-STOP accepted and reports latched', c == 200 and p.get('latched') is True, f'{c} {p.get("message")}')
        check('backend latched the mux stop', rig.wait_latched(True, 1.0), str(rig.policy and rig.policy.get('stop_reason')))
        time.sleep(2.0); stop_loop.set(); th.join()
        late = [x for x in codes_after[1:]]   # the first may race the e_stop
        check('no drive accepted after E-STOP while a client keeps posting drive', late and all(x == 409 for x in late), f'{len(late)} responses {set(late)}')
        check('mux output stayed at zero after E-STOP', not rig.moving_since(estop_at[0] + 0.15), f'{len(rig.moving_since(estop_at[0] + 0.15))} non-zero')
        check('web channel carried no motion after E-STOP', not rig.moving_since(estop_at[0] + 0.15, 'web'))

        # ---- loss of network / browser / remote cannot release ----
        time.sleep(5); check('no HTTP traffic for 5 s: still latched', rig.latched() is True)
        s = socket.create_connection(('127.0.0.1', PORT)); s.sendall(b'POST / HTTP/1.1\r\nHost: x\r\nContent-Length: 50\r\n\r\naction=re'); s.close()
        time.sleep(1); check('half-sent request then dropped connection: still latched', rig.latched() is True)
        server.send_signal(signal.SIGKILL); server.wait(); t_kill = time.monotonic(); time.sleep(3)
        check('web server killed (browser/network gone): still latched', rig.latched() is True)
        check('no motion while the web server is down', not rig.moving_since(t_kill))
        server = start_server(); c, _ = drive('p2', start=True)
        check('after web server restart: drive refused (latch survives restart)', c == 409 and rig.latched() is True, str(c))
        rig.joy('none', 2.0); check('remote signal lost for 2 s: still latched', rig.latched() is True, str(rig.policy and rig.policy.get('stop_reason')))
        rig.joy('neutral', 0.5); rig.joy('B', 0.3); rig.joy('neutral', 0.5)
        check('B pressed while latched: still latched', rig.latched() is True)
        for action in ('stop', 'reset', 'release', 'remote_stop_reset', 'clear'):
            post({'action': action})
        time.sleep(0.5); check('no web action releases the latch', rig.latched() is True)

        # ---- stops during shutdown ----
        server.send_signal(signal.SIGUSR1); time.sleep(0.3)
        r = {a: post(d)[0] for a, d in (('stop', {'action': 'stop'}), ('e_stop', {'action': 'e_stop'}),
                                        ('drive', {'action': 'drive', 'linear': '.3', 'angular': '0', 'press': 'p3', 'start': '1'}),
                                        ('camera', {'action': 'camera', 'axis': 'pan', 'direction': '1'}))}
        check('shutdown pending: stop and e_stop accepted (200)', r['stop'] == 200 and r['e_stop'] == 200, str(r))
        check('shutdown pending: drive and camera refused (409)', r['drive'] == 409 and r['camera'] == 409, str(r))
        server.send_signal(signal.SIGUSR2)

        # ---- release with the remote; nothing resumes by itself ----
        held, released = remote_release(rig); t_rel = time.monotonic()
        check('remote release after all of the above', released)
        time.sleep(2.0)
        check('after release: no motion without a new command (nothing replayed)', not rig.moving_since(t_rel - 0.1))
        c, _ = drive('p4', start=True); post({'action': 'stop'})
        check('after release: a fresh drive command is accepted', c == 200, str(c))
        post({'action': 'e_stop'}); check('test ends latched', rig.wait_latched(True, 1.0))
        if '--reset' in sys.argv:
            server = reset_tests(rig, server)
    finally:
        EVID['log'] = LOG; EVID['failures'] = FAIL
        for proc in (server, mux):
            if proc and proc.poll() is None:
                proc.terminate()
                try: proc.wait(5)
                except subprocess.TimeoutExpired: proc.kill()
        open(OUT, 'w').write(json.dumps(EVID, indent=1))
        print('FAILURES', len(FAIL)); os._exit(1 if FAIL else 0)


def reset_tests(rig, server):
    PIN = os.environ['E2E_PIN']
    def quiet_ready(extra=0.0):
        rig.joy('neutral', 1.7 + extra)     # remote neutral >= 1 s and no drive request for > 1.5 s
    log('--- web reset (stage 1b) ---')
    quiet_ready(); s = get_state()
    check('reset: latched, remote neutral, rover still, no drive -> RESET AVAILABLE', s['latched'] is True and s['reset']['available'], str(s['reset']['blocked']))
    # wrong confirmation / cross-site / bad nonce never reach the mux
    check('reset: missing confirmation rejected', post_reset(s['reset']['challenge'], PIN, confirm='yes')[0] == 400)
    check('reset: request without dashboard origin header rejected', post_reset(get_state()['reset']['challenge'], PIN,
          headers={'Content-Type': 'application/json'})[0] == 403)
    check('reset: forged challenge rejected', post_reset('forged', PIN)[0] == 409)
    check('reset: still latched after rejected attempts', rig.latched() is True)
    # unsafe or unknown conditions
    rig.odom_vx = 0.2; time.sleep(0.4); s = get_state(); rig.odom_vx = 0.0
    check('reset: rover moving -> RESET BLOCKED', not s['reset']['available'] and 'rover not stationary' in s['reset']['blocked'], str(s['reset']['blocked']))
    rig.joy('none', 1.0); s = get_state()
    check('reset: remote disconnected -> RESET BLOCKED', not s['reset']['available'] and 'physical remote not connected' in s['reset']['blocked'], str(s['reset']['blocked']))
    quiet_ready(); drive('p5', start=True); s = get_state()
    check('reset: a drive request in the last 1.5 s -> RESET BLOCKED', not s['reset']['available'], str(s['reset']['blocked']))
    quiet_ready(); server.send_signal(signal.SIGUSR1); time.sleep(0.2); s = get_state(); server.send_signal(signal.SIGUSR2)
    check('reset: shutdown pending -> RESET BLOCKED', 'shutdown in progress' in s['reset']['blocked'])
    # mux is the final authority: a deflected stick passes the server's checks but the mux refuses
    quiet_ready(); n = get_state()['reset']['challenge']; rig.joy('stick', 0.3)
    c, p = post_reset(n, PIN); rig.joy('neutral', 0.1)
    check('reset: stick deflected -> mux refuses, latch kept', c == 409 and rig.latched() is True, f'{c} {p.get("message")}')
    # a server restart (network/browser loss) drops every outstanding challenge
    quiet_ready(); n = get_state()['reset']['challenge'] if get_state()['reset']['available'] else None
    server.send_signal(signal.SIGKILL); server.wait(); server = start_server(); quiet_ready()
    c, _ = post_reset(n or 'none', PIN)
    check('reset: challenge from before a server restart (network loss) is rejected', c == 409 and rig.latched() is True, str(c))
    # granted reset: zero throughout, nothing resumes, fresh press required
    drive('pre', start=True)                 # a press that began while latched (refused; its start is recorded)
    quiet_ready(); n = get_state()['reset']['challenge']; t0 = time.monotonic()
    c, p = post_reset(n, PIN)
    check('reset: correct PIN + confirmation + safe state -> released', c == 200 and p.get('released') is True and rig.wait_latched(False, 1.5), f'{c} {p.get("message")}')
    time.sleep(2.0)
    check('reset: motor output stayed zero during and after the reset', not rig.moving_since(t0 - 0.2), f'{len(rig.moving_since(t0 - 0.2))} non-zero')
    codes = {'pre': [], 'lost': [], 'legacy': []}
    for _ in range(8):
        codes['pre'].append(drive('pre')[0]); codes['lost'].append(drive('lost')[0]); codes['legacy'].append(drive()[0]); time.sleep(0.12)
    check('reset: repeats of a press begun before the reset are refused', set(codes['pre']) == {409}, str(codes['pre']))
    check('reset: repeats of a press whose start never arrived (network outage) are refused', set(codes['lost']) == {409})
    check('reset: an old page without press ids is refused', set(codes['legacy']) == {409})
    check('reset: no motion from any of them', not rig.moving_since(t0 - 0.2))
    t1 = time.monotonic(); c, _ = drive('fresh', start=True); c2, _ = drive('fresh'); time.sleep(0.2); post({'action': 'stop'})
    check('reset: a fresh press after the reset drives', c == 200 and c2 == 200 and bool(rig.moving_since(t1, 'web')), f'{c} {c2}')
    c, p = post({'action': 'e_stop'}); check('reset: E-STOP latches again afterwards', c == 200 and rig.wait_latched(True, 1.0))
    # wrong PIN lockout
    for _ in range(5):
        quiet_ready(0.0); post_reset(get_state()['reset']['challenge'], '000000')
    s = get_state(); c, _ = post_reset('x', PIN)
    check('reset: 5 wrong PINs -> locked out (429) even with the right PIN', c == 429 and s['reset']['lockout_s'] > 0 and rig.latched() is True, f'{c} lockout {s["reset"]["lockout_s"]}')
    # event log
    events = [json.loads(l) for l in open(os.environ['ATLAS_ESTOP_EVENT_LOG'])]
    kinds = {e['event'] for e in events}
    check('reset: stop, e_stop, denied, granted and latch-state events logged', {'stop', 'e_stop', 'reset_denied', 'reset_denied_pin', 'reset_granted', 'latch_state'} <= kinds, str(sorted(kinds)))
    check('reset: PIN never written to the event log', PIN not in open(os.environ['ATLAS_ESTOP_EVENT_LOG']).read())
    EVID['event_log_sample'] = events[-12:]
    return server


if __name__ == '__main__':
    main()
