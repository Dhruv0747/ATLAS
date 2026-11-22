"""One-click Stage-3 round trip (2026-11-22 owner request: "one click and it does everything").

The runner only does what the owner would otherwise do by hand on the dashboard, in the right order:
  1. POSITION  if ATLAS is not at the round-trip start pose, send "Go dhruv room" (the taught route ends there,
               facing into the room) and wait for SUCCEEDED; then wait until ATLAS is still.
  2. RECORD    start a bag of the Stage-3 checker topics.
  3. OUT       send "Go hall"; ask the owner to press B (safe stop) once while ATLAS is rolling.
  4. HOME      send "Go dhruv room".
  5. CHECK     stop the bag and run stage3_autonomy_check.py; show the five verdicts.
A failed/cancelled leg (doorway, E-STOP, network) is re-sent automatically once ATLAS has been still for a few
seconds, autonomy is ON again and the E-STOP is released, so the owner only helps with the remote.

Authority does NOT change: goals go through the same /atlas/navigate_named_place path as the Go buttons
(refused unless autonomy is ON and the E-STOP is released); mission control and the cmd_vel mux keep every check.
The runner never arms autonomy, never releases the E-STOP, never presses B and never sends velocity.

`Runner` is pure (no ROS, no threads): step(obs) -> list of actions. The IO wrapper lives in the status web.
"""
import math
import re

HOME, OUT = 'dhruv room', 'hall'
START_X, START_Y, START_YAW_DEG = 0.28, 0.66, 105.0      # taught-route home pose (arrival heading, into the room)
START_TOL_M, START_TOL_DEG = 0.25, 15.0
STILL_S = 5.0                 # ATLAS must be still this long before any goal is (re)sent
STILL_M = 0.03
STILL_DEG = 3.0
B_PROMPT_SPEED = 0.08         # m/s: "PRESS B NOW" only while clearly rolling (checker needs >= 0.05 at the press)
B_PROMPT_MIN_S = 1.0
RETRY_GAP_S = 8.0
FINISHED = re.compile(r'NAMED GOAL FINISHED name=(.+?) status=(\d+)')
ACCEPTED = re.compile(r'NAMED GOAL (?:ACCEPTED|DISPATCHED) name=(.+)$')


def _place(text):
    return re.sub(r'\s+taught-route$', '', text.strip().lower())


def _dyaw(a, b):
    return (a - b + 180.0) % 360.0 - 180.0


class Runner:
    def __init__(self):
        self.state = 'IDLE'
        self.message = 'Press START to run the Stage-3 round trip.'
        self.leg = None
        self.leg_sent_t = None
        self.leg_accepted = False
        self.last_fail_t = -1e9
        self.attempts = {OUT: 0, HOME: 0}
        self.still_since = None
        self.last_pose = None
        self.rolling_since = None
        self.stop_done = False
        self.b_prompt = False
        self.log = []
        self.result = None
        self.started_t = None
        self.last_mission = None

    # ---------------------------------------------------------------------------------------------------------------
    def _say(self, t, text):
        self.message = text
        if not self.log or self.log[-1][1] != text:
            self.log.append((round(t, 1), text))
            del self.log[:-40]

    def start(self, t):
        if self.state not in ('IDLE', 'DONE', 'CANCELLED', 'ERROR'):
            return False, 'A Stage-3 run is already in progress.'
        self.__init__()
        self.state, self.started_t = 'POSITION', t
        self._say(t, 'Starting: checking the start pose.')
        return True, 'Stage-3 run started.'

    def cancel(self, t):
        if self.state in ('IDLE', 'DONE', 'CANCELLED'):
            return []
        actions = [('stop_recording', 'cancelled')] if self.state in ('OUT', 'HOME', 'CHECK') else []
        self.state = 'CANCELLED'
        self._say(t, 'Cancelled by the owner. Use the remote / Abort to stop ATLAS if it is moving.')
        return actions

    def finish_check(self, t, verdicts):
        self.result = verdicts
        self.state = 'DONE'
        ok = verdicts.get('verdict') == 'PASS'
        self._say(t, 'STAGE 3 PASS!' if ok else 'Stage 3 checker: FAIL. See the five checks below.')

    # ---------------------------------------------------------------------------------------------------------------
    def _update_still(self, t, obs):
        pose = obs.get('pose')
        if pose is None:
            self.still_since, self.last_pose = None, None
            return
        moved = (self.last_pose is None or math.hypot(pose[0] - self.last_pose[0], pose[1] - self.last_pose[1]) > STILL_M
                 or abs(_dyaw(pose[2], self.last_pose[2])) > STILL_DEG or abs(obs.get('speed') or 0.0) > 0.02)
        if moved:
            self.still_since, self.last_pose = t, pose
        elif self.still_since is None:
            self.still_since = t

    def _still_for(self, t):
        return 0.0 if self.still_since is None else t - self.still_since

    def _ready(self, obs):
        """Why a goal cannot be sent now ('' = ready). Mirrors the dashboard Go refusal + mission-control idle."""
        if obs.get('latched') is not False:
            return 'E-STOP is latched: release it with the remote.'
        if obs.get('armed') is not True:
            return 'Autonomy is OFF: turn AUTONOMY ON (PIN).'
        if obs.get('pose') is None:
            return 'Location not available.'
        if (obs.get('xy_std') is None) or obs['xy_std'] > 0.15:
            return 'Location not confident yet.'
        return ''

    def at_start(self, pose):
        return (pose is not None and math.hypot(pose[0] - START_X, pose[1] - START_Y) <= START_TOL_M
                and abs(_dyaw(pose[2], START_YAW_DEG)) <= START_TOL_DEG)

    def _send(self, t, place):
        self.leg, self.leg_sent_t, self.leg_accepted = place, t, False
        self.attempts[place] = self.attempts.get(place, 0) + 1
        return [('go', place)]

    def _mission_event(self, obs):
        m = obs.get('mission') or ''
        if m == self.last_mission:
            return None
        self.last_mission = m
        f = FINISHED.search(m)
        if f:
            return ('finished', _place(f.group(1)), int(f.group(2)))
        a = ACCEPTED.search(m)
        if a:
            return ('accepted', _place(a.group(1)), None)
        if m.startswith('ERROR'):
            return ('error', None, m)
        return None

    # ---------------------------------------------------------------------------------------------------------------
    def step(self, t, obs):
        """obs: pose (x, y, yaw_deg) | None, speed (m/s), xy_std, latched (bool|None), armed (bool|None),
        mission (str), source (str). Returns a list of actions: ('go', place), ('start_recording',),
        ('stop_recording', reason), ('run_checker',)."""
        self._update_still(t, obs)
        ev = self._mission_event(obs)
        actions = []
        self.b_prompt = False
        st = self.state
        if st in ('IDLE', 'DONE', 'CANCELLED', 'ERROR', 'CHECK'):
            return actions

        if st == 'POSITION':
            if self.leg == HOME and ev and ev[0] == 'finished' and ev[1] == HOME:
                if ev[2] == 4:
                    self.state = 'SETTLE'; self.leg = None
                    self._say(t, 'At the start. Hands off the remote: waiting until ATLAS is still.')
                else:
                    self.leg = None; self.last_fail_t = t
                    self._say(t, 'Going to the start did not finish. Help ATLAS with the remote if needed; it retries by itself.')
                return actions
            if self.leg == HOME and ev and ev[0] == 'error':
                self.leg = None; self.last_fail_t = t
                self._say(t, 'Mission control refused: ' + ev[2][:120])
                return actions
            if self.leg is None:
                if self.at_start(obs.get('pose')) and self._still_for(t) >= 1.0:
                    self.state = 'SETTLE'
                    self._say(t, 'At the start. Hands off the remote: waiting until ATLAS is still.')
                    return actions
                why = self._ready(obs)
                if why:
                    self._say(t, 'To go to the start: ' + why); return actions
                if self._still_for(t) < STILL_S or t - self.last_fail_t < RETRY_GAP_S:
                    self._say(t, 'Waiting for ATLAS to be still before going to the start...'); return actions
                self._say(t, 'Going to the start pose (Go dhruv room)...')
                return self._send(t, HOME)
            return actions

        if st == 'SETTLE':
            pose = obs.get('pose')
            if not self.at_start(pose):
                self.state = 'POSITION'; self.leg = None
                self._say(t, 'ATLAS left the start pose. Going back to the start...')
                return actions
            why = self._ready(obs)
            if why:
                self._say(t, 'Before the run: ' + why); return actions
            if self._still_for(t) < STILL_S:
                self._say(t, 'Hands off the remote: waiting %.0f s more...' % (STILL_S - self._still_for(t))); return actions
            self.state = 'OUT'
            self._say(t, 'Recording started. Going to the hall. Press B once when the screen says PRESS B NOW.')
            return [('start_recording',)] + self._send(t, OUT)

        # OUT / HOME legs -------------------------------------------------------------------------------------------
        place = OUT if st == 'OUT' else HOME
        speed = abs(obs.get('speed') or 0.0)
        if ev and ev[0] == 'accepted' and ev[1] == place:
            self.leg_accepted = True
        if self.leg == place and self.leg_accepted and not self.stop_done and obs.get('source') == 'NAV2' \
                and speed >= B_PROMPT_SPEED and obs.get('latched') is False:
            self.rolling_since = self.rolling_since or t
            if t - self.rolling_since >= B_PROMPT_MIN_S:
                self.b_prompt = True
        else:
            self.rolling_since = None
        if obs.get('latched') is True and self.leg == place and self.leg_accepted and not self.stop_done \
                and speed >= 0.05:
            self.stop_done = True
            self._say(t, 'Safe stop recorded. Release the E-STOP and turn AUTONOMY ON: the run continues by itself.')
        if ev and ev[0] == 'finished' and ev[1] == place:
            if ev[2] == 4:
                if place == OUT:
                    self.state = 'HOME'; self.leg = None; self.last_fail_t = t - RETRY_GAP_S
                    self._say(t, 'Hall reached. Going back to dhruv room' +
                              ('.' if self.stop_done else ' - press B once when the screen says PRESS B NOW.'))
                else:
                    if not self.stop_done:
                        self._say(t, 'Back home, but no safe stop (B) was recorded while rolling: the checker will FAIL safe_stop.')
                    self.state = 'CHECK'
                    return [('stop_recording', 'done'), ('run_checker',)]
                return actions
            self.leg = None; self.last_fail_t = t
            self._say(t, ('Stopped (%s). ' % {5: 'cancelled', 6: 'failed'}.get(ev[2], 'status %d' % ev[2])) +
                      'Help ATLAS out of any doorway with the remote, then release the remote: it continues by itself.')
            return actions
        if ev and ev[0] == 'error':
            self.leg = None; self.last_fail_t = t
            self._say(t, 'Mission control refused: ' + ev[2][:120] + ' - it retries when ATLAS is still in open space.')
            return actions
        if self.leg is None:
            why = self._ready(obs)
            if why:
                self._say(t, ('Safe stop done. ' if self.stop_done else '') + why); return actions
            if self._still_for(t) < STILL_S or t - self.last_fail_t < RETRY_GAP_S:
                return actions
            self._say(t, 'Sending Go %s (attempt %d)...' % (place, self.attempts.get(place, 0) + 1))
            return self._send(t, place)
        return actions

    def snapshot(self):
        return {'state': self.state, 'message': self.message, 'leg': self.leg, 'stop_done': self.stop_done,
                'press_b_now': self.b_prompt, 'attempts': dict(self.attempts), 'log': list(self.log),
                'result': self.result,
                'start_pose': {'x': START_X, 'y': START_Y, 'yaw_deg': START_YAW_DEG,
                               'tol_m': START_TOL_M, 'tol_deg': START_TOL_DEG}}


# ===================================================================================================================
# IO wrapper (status web). Everything external is injected so it can be tested without ROS.
# ===================================================================================================================
import json
import os
import signal
import subprocess
import threading
import time
from pathlib import Path

BAG_DIR = Path.home() / 'atlas_bags'
CHECKER = Path(__file__).resolve().parents[1] / 'tools' / 'drive' / 'stage3_autonomy_check.py'
TOPICS = ['/atlas/mission_status', '/atlas/motion_safety', '/atlas/encoder_health', '/amcl_pose', '/cmd_vel',
          '/cmd_vel_joy', '/cmd_vel_nav', '/yahboom/odom', '/im10a/imu/bias_corrected_candidate',
          '/atlas/control_policy', '/scan', '/tf', '/tf_static', '/ultrasonic/validity', '/joy']
ROS_ENV = ('source /opt/ros/humble/setup.bash; source /home/jetson/project_atlas_ws/install/setup.bash 2>/dev/null; '
           'export FASTDDS_BUILTIN_TRANSPORTS=UDPv4 ROS_LOCALHOST_ONLY=0; unset ROS_DOMAIN_ID; ')
CONFIRM = 'STAGE3'
LINE = re.compile(r'^(PASS|FAIL)\s+(\w+)\s+(.*)$')


class Recorder:
    def __init__(self, popen=subprocess.Popen, bag_dir=BAG_DIR):
        self.popen, self.bag_dir, self.proc, self.path = popen, Path(bag_dir), None, None

    def start(self):
        self.bag_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.bag_dir / ('stage3_auto_' + time.strftime('%Y%m%d_%H%M%S'))
        cmd = ROS_ENV + 'exec nice -n 5 ros2 bag record -o %s %s' % (self.path, ' '.join(TOPICS))
        log = open(str(self.path) + '.log', 'w')
        self.proc = self.popen(['bash', '-lc', cmd], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        return str(self.path)

    def stop(self, timeout_s=15.0):
        p, self.proc = self.proc, None
        if p is None:
            return
        try:
            os.killpg(p.pid, signal.SIGINT)
            p.wait(timeout=timeout_s)
        except (ProcessLookupError, subprocess.TimeoutExpired, OSError):
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except OSError:
                pass

    def running(self):
        return self.proc is not None and self.proc.poll() is None


def run_checker(bag, runner=subprocess.run):
    cmd = ROS_ENV + 'exec nice -n 10 /usr/bin/python3 %s %s --home "dhruv room"' % (CHECKER, bag)
    try:
        out = runner(['bash', '-lc', cmd], capture_output=True, text=True, timeout=900).stdout
    except subprocess.TimeoutExpired:
        return {'verdict': 'ERROR', 'checks': {}, 'raw': 'checker timed out'}
    checks = {}
    for line in out.splitlines():
        m = LINE.match(line.strip())
        if m:
            checks[m.group(2)] = {'ok': m.group(1) == 'PASS', 'detail': m.group(3).strip()}
    verdict = 'PASS' if 'STAGE 3: PASS' in out else ('FAIL' if 'STAGE 3: FAIL' in out else 'ERROR')
    return {'verdict': verdict, 'checks': checks, 'raw': out[-2000:]}


class Service:
    """Ticks the Runner every 0.5 s. obs_fn() -> obs dict; go_fn(place) -> (ok, message)."""

    def __init__(self, obs_fn, go_fn, recorder=None, checker=run_checker, clock=time.monotonic, period=0.5):
        self.runner, self.obs_fn, self.go_fn = Runner(), obs_fn, go_fn
        self.recorder, self.checker, self.clock, self.period = recorder or Recorder(), checker, clock, period
        self.lock = threading.Lock()
        self.bag = None
        self.thread = None

    def start(self):
        with self.lock:
            ok, msg = self.runner.start(self.clock())
        if ok and (self.thread is None or not self.thread.is_alive()):
            self.thread = threading.Thread(target=self._loop, name='stage3-runner', daemon=True)
            self.thread.start()
        return ok, msg

    def cancel(self):
        with self.lock:
            acts = self.runner.cancel(self.clock())
        self._do(acts)
        return True, 'Stage-3 run cancelled.'

    def snapshot(self):
        with self.lock:
            snap = self.runner.snapshot()
        snap['bag'] = self.bag
        snap['recording'] = self.recorder.running()
        return snap

    def _do(self, actions):
        for a in actions:
            if a[0] == 'go':
                ok, msg = self.go_fn(a[1])
                if not ok:
                    with self.lock:
                        self.runner.leg = None
                        self.runner.last_fail_t = self.clock()
                        self.runner._say(self.clock(), 'Go %s not sent: %s' % (a[1], msg))
            elif a[0] == 'start_recording':
                self.bag = self.recorder.start()
            elif a[0] == 'stop_recording':
                self.recorder.stop()
            elif a[0] == 'run_checker':
                res = self.checker(self.bag) if self.bag else {'verdict': 'ERROR', 'checks': {}, 'raw': 'no bag'}
                with self.lock:
                    self.runner.finish_check(self.clock(), res)

    def tick(self):
        try:
            obs = self.obs_fn()
        except Exception as exc:          # never let a bad status read kill the run; send nothing this tick
            obs = {}
            with self.lock:
                self.runner._say(self.clock(), 'Status read error: %s' % str(exc)[:80])
        with self.lock:
            acts = self.runner.step(self.clock(), obs)
        self._do(acts)

    def _loop(self):
        while True:
            with self.lock:
                st = self.runner.state
            if st in ('IDLE', 'DONE', 'CANCELLED', 'ERROR'):
                return
            self.tick()
            time.sleep(self.period)


def serve(handler, service, json_response, post=False):
    """/api/stage3: GET -> snapshot; POST {action: start|cancel, confirm: STAGE3} from the dashboard page only."""
    from urllib.parse import urlsplit
    if urlsplit(handler.path).path != '/api/stage3':
        return False
    if not post:
        json_response(handler, 200, service.snapshot())
        return True
    try:
        from atlas_wifi_web import same_origin
        length = int(handler.headers.get('Content-Length', '0'))
        if not 0 < length <= 256 or handler.headers.get_content_type() != 'application/json':
            raise ValueError('bounded JSON request required')
        payload = json.loads(handler.rfile.read(length))
        if not isinstance(payload, dict) or payload.get('confirm') != CONFIRM:
            raise ValueError('dashboard confirmation required')
        if not same_origin(handler.headers):
            raise PermissionError('request did not come from the ATLAS dashboard page')
    except PermissionError as exc:
        json_response(handler, 403, {'ok': False, 'message': str(exc)}); return True
    except (ValueError, TypeError) as exc:
        json_response(handler, 400, {'ok': False, 'message': str(exc)}); return True
    action = payload.get('action')
    if action == 'start':
        ok, msg = service.start()
        json_response(handler, 202 if ok else 409, {'ok': ok, 'message': msg})
    elif action == 'cancel':
        ok, msg = service.cancel()
        json_response(handler, 200, {'ok': ok, 'message': msg})
    else:
        json_response(handler, 400, {'ok': False, 'message': 'unknown action'})
    return True
