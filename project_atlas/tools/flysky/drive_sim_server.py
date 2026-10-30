#!/usr/bin/env python3
"""Offline simulator for the FlySky Driving page (controller visualisation + remote selection). No ROS, no hardware.

Serves /v2/ statics and the REAL page backends with fake inputs:
  /api/manual_controller  atlas_manual_controller_web.serve  (fake mux policy, drive status and select services)
  /api/flysky/state       atlas_flysky_web.serve              (FlyskyService fed simulated SBUS frames)
  /api/controller_inputs  atlas_controller_input_web.serve    (InputService fed simulated /joy at 20 Hz)
Change the scene:  /sim?scenario=<name>     names: see SCENARIOS.
Usage: drive_sim_server.py --port 8203 [--scenario live]
"""
import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace as NS
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import atlas_flysky_core as C              # noqa: E402
import atlas_flysky_web as FW              # noqa: E402
import atlas_manual_controller_web as MW   # noqa: E402
import atlas_controller_input_web as IW    # noqa: E402
import atlas_web_v2                        # noqa: E402

UP, MID, DOWN = 240, 1024, 1807
CONFIG = {'enabled': False, 'errors': ['FlySky driving gate is off (ATLAS_FLYSKY_DRIVE_ENABLED is not 1)',
                                       'config has not been reviewed and accepted by the owner (reviewed_by_owner: true)'],
          'reviewed_by_owner': False, 'throttle': {'channel': 2, 'reversed': False, 'deadband': 0.08},
          'steering': {'channel': 1, 'reversed': True, 'deadband': 0.08}, 'arm_channel': 5, 'stop_channel': 6,
          'speed_mode_channel': 7, 'max_linear_mps': 0.15, 'max_angular_radps': 0.6,
          'hard_max_linear_mps': 0.25, 'hard_max_angular_radps': 0.8}
REST_AXES = [0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
SCENARIOS = ['live', 'xbox_demo', 'flysky_demo', 'flysky_selected', 'flysky_armed', 'xbox_driving',
             'rc_lost', 'rc_failsafe', 'xbox_lost', 'no_input_api', 'mismatch',
             'reset_blocked', 'reset_ready', 'reset_holding', 'reset_refused', 'reset_off']


def scene(name, t):
    """-> dict(policy, drive, rc (list of 16 raw or None), rc_failsafe, joy (axes, buttons) or None, inputs_api)."""
    pol = {'stop_latched': True, 'stop_reason': 'REMOTE STOP: joystick unavailable', 'source': 'STOPPED',
           'manual_controller': 'XBOX', 'flysky_drive_enabled': False}
    cfg = json.loads(json.dumps(CONFIG))
    rc = [MID] * 16
    rc[4] = rc[5] = rc[6] = rc[7] = UP
    rc[8] = rc[9] = MID
    axes, buttons = list(REST_AXES), [0] * 11
    state, reason = 'DISABLED', '; '.join(cfg['errors'])
    fsafe, joy_on, rc_on, api = False, True, True, True
    if name == 'xbox_demo':
        axes[1], axes[3], axes[6] = 0.62, -0.45, 1.0
        buttons[4], buttons[3] = 1, 1
        axes[5] = -0.2
    elif name == 'flysky_demo':
        rc[4], rc[6], rc[0], rc[1], rc[8] = DOWN, MID, 1380, 1560, 1500
    elif name in ('flysky_selected', 'flysky_armed', 'mismatch') or name.startswith('reset_'):
        cfg.update(enabled=True, errors=[], reviewed_by_owner=True, max_linear_mps=0.05, max_angular_radps=0.2)
        pol.update(manual_controller='FLYSKY', flysky_drive_enabled=True)
        state, reason = 'STOP_LATCHED', 'E-STOP latched'
        if name == 'flysky_armed':
            pol.update(stop_latched=False, stop_reason='', source='FLYSKY')
            rc[4], rc[1], rc[0] = DOWN, 1300, 900
            state, reason = 'ARMED', 'armed'
        if name == 'mismatch':
            cfg['steering']['channel'] = 4
    elif name == 'xbox_driving':
        pol.update(stop_latched=False, stop_reason='', source='REMOTE')
        axes[1], buttons[4] = 0.5, 1
    elif name == 'rc_lost':
        rc_on = False
        state, reason = 'NO_SIGNAL', 'no receiver frame'
    elif name == 'rc_failsafe':
        fsafe = True
        state, reason = 'FAILSAFE', 'receiver failsafe'
    elif name == 'xbox_lost':
        joy_on = False
    elif name == 'no_input_api':
        api = False
    thr = None if not rc_on else round((rc[1] - MID) / 783, 2)
    drive = {'state': state, 'reason': reason, 'armed': state == 'ARMED',
             'command': [0.03, -0.05] if state == 'ARMED' else None, 'stop_requested': False,
             'inputs': None if not rc_on else {'throttle': thr if abs(thr or 0) > 0.08 else 0.0, 'steering': 0.0,
                                               'arm': 'ON' if rc[4] > 1700 else 'OFF', 'stop': 'RUN' if rc[5] < 400 else 'STOP',
                                               'failsafe': fsafe, 'frame_lost': False,
                                               'speed_scale': 0.33 if rc[6] < 400 else 1.0 if rc[6] > 1700 else 0.66},
             'frame_age_s': 0.05 if rc_on else None, 'config': cfg, 'gate_env': 'ATLAS_FLYSKY_DRIVE_ENABLED'}
    if name.startswith('reset_'):          # Stage 29 FlySky reset status, as the teleop reports it
        mux = {'enabled': name != 'reset_off', 'last_result': None, 'last_reason': '', 'age_s': None, 'stationary': True}
        g = {'enabled': name != 'reset_off', 'state': 'READY', 'blocked': [], 'held_s': None, 'hold_s': 2.0, 'max_hold_s': 5.0,
             'channel': 8, 'switch': 'SwD', 'available': True, 'last_seq': 0, 'mux': mux}
        if name == 'reset_blocked':
            rc[4] = DOWN; drive['inputs']['arm'] = 'ON'
            g.update(state='BLOCKED', available=False, blocked=['SwA must be OFF (up)'])
        elif name == 'reset_holding':
            rc[7] = DOWN; g.update(state='HOLDING', held_s=1.2)
        elif name == 'reset_refused':
            g.update(state='WAIT_SWD_UP', available=False)
            mux.update(last_result='REFUSED', last_reason='rover not confirmed stationary (encoders fresh, healthy and still for 1 s)',
                       age_s=1.4, stationary=False)
        drive['reset'] = g
    return {'policy': pol, 'drive': drive, 'rc': rc if rc_on else None, 'rc_failsafe': fsafe,
            'joy': (axes, buttons) if joy_on else None, 'inputs_api': api}


class FakeFuture:
    def __init__(self, ok, msg): self.r = NS(success=ok, message=msg)
    def done(self): return True
    def result(self): return self.r
    def cancel(self): pass


class Sim:
    def __init__(self, name):
        self.name, self.t0, self.forced = name, time.monotonic(), {}
        self.ready = True
        self.manual_controller_clients = {t: self._client(t) for t in ('XBOX', 'FLYSKY')}
        self.estop_log = NS(write=lambda *a, **k: None)
        self.fs = FW.FlyskyService(lambda: NS(start=lambda cb: None, publisher_count=lambda: 1, stop=lambda: None),
                                   Path('/tmp/atlas_drive_sim_flysky'), start_threads=False)
        self.inp = IW.InputService(lambda: NS(start=lambda cb: None, stop=lambda: None), start_threads=False)
        threading.Thread(target=self.loop, daemon=True).start()

    def now(self):
        s = scene(self.name, time.monotonic() - self.t0)
        s['policy'].update(self.forced)
        return s

    def _client(self, target):
        sim = self

        class Client:
            srv_type = NS(Request=lambda: object())
            def service_is_ready(self): return True
            def call_async(self, req):
                s = sim.now()
                if s['policy']['stop_latched'] is not True:
                    return FakeFuture(False, 'Latch the E-STOP before changing controller')
                sim.forced['manual_controller'] = target
                return FakeFuture(True, 'Manual controller is %s. E-STOP stays latched.' % target)
        return Client()

    def _item(self, key):
        s = self.now()
        if key == 'control_policy':
            return {'value': json.dumps(s['policy']), 'ts': time.time()}
        if key == 'flysky_drive':
            return {'value': json.dumps(s['drive']), 'ts': time.time()}
        return None

    def loop(self):
        k = 0
        while True:
            time.sleep(0.05)
            k += 1
            s = self.now()
            if s['joy'] is not None:
                self.inp._on_message(*s['joy'])
            if s['rc'] is not None and k % 2 == 0:
                self.fs._on_message(json.dumps({'proto': 'sbus', 'hex': C.encode_sbus(s['rc'], failsafe=s['rc_failsafe']).hex()}))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8203)
    ap.add_argument('--scenario', default='live', choices=SCENARIOS)
    a = ap.parse_args()
    sim = Sim(a.scenario)

    class H(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            p = urlsplit(self.path)
            if p.path == '/sim':
                q = parse_qs(p.query)
                name = q.get('scenario', [sim.name])[0]
                if name in SCENARIOS:
                    sim.name, sim.t0, sim.forced = name, time.monotonic(), {}
                    with sim.fs.lock:
                        sim.fs.lab = C.FlyskyLab()
                    with sim.inp.lock:
                        sim.inp.last, sim.inp.rx_times = None, []
                body = json.dumps({'scenario': sim.name}).encode()
                self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
                return
            if MW.serve(self, sim):
                return
            if p.path == IW.ROUTE and not sim.now()['inputs_api']:
                self.send_error(404); return
            if IW.serve(self, sim, svc=sim.inp):
                return
            if FW.serve(self, service=sim.fs):
                return
            if atlas_web_v2.handles(self.path):
                atlas_web_v2.serve(self)
                return
            self.send_error(404)

        def do_POST(self):
            self.headers.get_content_type = lambda: self.headers.get('Content-Type', '').split(';')[0]
            if MW.serve(self, sim, post=True):
                return
            n = int(self.headers.get('Content-Length', '0'))
            self.rfile.read(n)
            body = b'{"message":"Simulated stop (nothing connected)."}'
            self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(body)))
            self.end_headers(); self.wfile.write(body)

    ThreadingHTTPServer(('127.0.0.1', a.port), H).serve_forever()


if __name__ == '__main__':
    main()
