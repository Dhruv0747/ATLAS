"""Web/ROS adapter for the opt-in Stage 17B server delegation.

Uses existing steering requests and the existing stop-only input. A recorder
child is finite and starts only after an enabled, confirmed Prepare request.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from atlas_single_person_steering import SinglePersonSteering, TERMINAL, measurement_report


class SinglePersonSteeringService:
    def __init__(self, ros, string_type, empty_type, *, root=None, enabled=None, shutdown_check=lambda: False):
        self.ros, self.String, self.Empty = ros, string_type, empty_type
        self.root = Path(root or Path(__file__).resolve().parents[1] / 'data/diagnostics/stage17b')
        self.lock = threading.RLock()
        self.recorder = None
        self.log = None
        self.recorder_stop_at = None
        self.last_status_at = -1e9
        self.shutdown_check = shutdown_check
        flag = os.environ.get('ATLAS_STAGE17B_ENABLED', '0') == '1' if enabled is None else enabled
        self.engine = SinglePersonSteering(self._send, self._stop, self._event, self._announce, enabled=flag)

    def _send(self, command):
        self.ros.steering_cal_pub.publish(self.String(data=json.dumps(command)))

    def _stop(self, reason):
        if self.ros.commissioning_stop_pub is not None:
            self.ros.commissioning_stop_pub.publish(self.Empty())

    def _announce(self, text):
        if getattr(self.ros, 'steering_test_speech_pub', None) is not None:
            self.ros.steering_test_speech_pub.publish(self.String(data=text))

    def _event(self, event):
        event['ros_time_ns'] = self.ros.node.get_clock().now().nanoseconds
        pub = getattr(self.ros, 'steering_test_event_pub', None)
        if pub is not None:
            pub.publish(self.String(data=json.dumps(event)))
        self.root.mkdir(parents=True, exist_ok=True)
        # One finite report per UUID session; no existing evidence is pruned.
        target = self.root / ('session_' + self.engine.owner_session + '.json')
        temp = target.with_suffix('.tmp')
        temp.write_text(json.dumps(self.engine.status(time.monotonic()), indent=2)+'\n', encoding='utf-8')
        os.replace(temp, target)

    def observations(self):
        def item(key, age=0.6):
            data = self.ros._item(key)
            if not data or not 0 <= time.time()-data.get('ts', 0) <= age:
                return None
            value = data.get('value')
            if isinstance(value, str):
                try: return json.loads(value)
                except (ValueError, TypeError): return None
            return value
        def obj(key):
            value = item(key)
            return value if isinstance(value, dict) else None
        policy, owner = obj('control_policy'), obj('steering_calibration')
        command, encoders, gyro = obj('cmd_vel'), obj('encoder_health'), obj('imu_full')
        scan = getattr(self.ros, 'surround_scan', None)
        safe = (self.ros.ready and not self.shutdown_check() and policy is not None and policy.get('stop_latched') is True
                and command is not None and command.get('lin') == 0 and command.get('ang') == 0
                and owner is not None and owner.get('zero_motor_command') is True
                and owner.get('applied_motor_outputs') == [0, 0, 0, 0]
                and owner.get('remote_b_stop') is False
                and encoders is not None and encoders.get('packet_fresh') is True
                and encoders.get('serial_write_errors') == 0
                and gyro is not None and scan is not None and 0 <= time.time()-scan[1] <= .6)
        health_path = self.root / 'bags/recorder_health.json'
        record_ready = False
        if self.recorder is not None and self.recorder.poll() is None and health_path.exists():
            try:
                health = json.loads(health_path.read_text())
                record_ready = (0 <= time.time()-health_path.stat().st_mtime <= 2
                    and health.get('profile') == 'steering-validation'
                    and health.get('preroll_ready') is True and not health.get('disabled')
                    and not health.get('missing') and not health.get('stale')
                    and health.get('state') in ('READY', 'RECORDING'))
            except (OSError, ValueError):
                pass
        return {'safe': bool(safe), 'shutdown': bool(self.shutdown_check()), 'owner': owner or {}, 'recorder_ready': record_ready,
                'front_applied': item('front_steer'), 'rear_applied': item('rear_steer'),
                'problem': 'fresh latched stop, released B button, zero-traction owner, LiDAR/IMU/encoder link required'}

    def _start_recorder(self):
        self.root.mkdir(parents=True, exist_ok=True)
        self.log = (self.root / ('recorder_' + self.engine.owner_session + '.log')).open('x', encoding='utf-8')
        self.recorder = subprocess.Popen([sys.executable,
            str(Path(__file__).with_name('atlas_motion_recorder.py')), '--record',
            '--profile', 'steering-validation', '--duration', '420', '--root', str(self.root/'bags')],
            stdout=self.log, stderr=subprocess.STDOUT)
        self.recorder_stop_at = None

    def _stop_recorder(self):
        if self.recorder is not None and self.recorder.poll() is None:
            self.recorder.terminate()  # Only our finite diagnostic child; never a robot service.
        if self.log is not None:
            self.log.close()
        self.recorder, self.log = None, None

    def command(self, payload):
        with self.lock:
            now, op = time.monotonic(), payload.get('op')
            client = payload.get('session')
            if op == 'emergency':
                self.engine.emergency(now)
            elif op == 'prepare':
                if self.recorder is not None and self.recorder.poll() is None:
                    raise ValueError('previous recorder is finishing its bounded post-roll')
                self._stop_recorder()
                self.engine.prepare(client, now, self.observations(), payload.get('confirmations', {}), payload.get('mode', 'caliper'))
                try: self._start_recorder()
                except Exception:
                    self.engine.cancel(now, 'diagnostic recorder could not start')
                    raise ValueError('recorder unavailable; test cancelled')
            elif op == 'start':
                self.engine.start(client, now, self.observations(), payload.get('approved') is True,
                                  payload.get('return_center') is True)
            elif op == 'pause': self.engine.pause(client, now)
            elif op == 'resume': self.engine.resume(client, now, payload.get('hands_clear') is True)
            elif op == 'cancel':
                self.engine.authorize(client); self.engine.cancel(now)
            elif op == 'measurements':
                self.engine.authorize(client)
                if self.engine.state not in ('COMPLETE', 'CANCELLED'):
                    raise ValueError('enter observations after the sequence has stopped')
                self.engine.measurements = measurement_report(payload.get('readings', []), payload.get('method'),
                    payload.get('uncertainty_deg', 2), payload.get('baselines'), payload.get('error_mm', 1))
                self.engine.event('observations_saved_only', now)
            else: raise ValueError('unsupported single-person test operation')
            return self.engine.status(now)

    def tick(self):
        with self.lock:
            now = time.monotonic()
            try:
                self.engine.tick(now, self.observations())
                if self.engine.state in TERMINAL and self.recorder is not None:
                    if self.recorder_stop_at is None: self.recorder_stop_at = now+25
                    if now >= self.recorder_stop_at: self._stop_recorder()
                if now-self.last_status_at >= .5:
                    status = self.engine.status(now)
                    self.ros._set('single_person_steering', status)
                    pub = getattr(self.ros, 'steering_test_status_pub', None)
                    if pub is not None: pub.publish(self.String(data=json.dumps(status)))
                    self.last_status_at = now
            except Exception:
                # Includes local storage failures; never renew a failed sequence.
                self.engine.state, self.engine.reason = 'CANCELLED', 'server diagnostic/safety failure'
                self._stop(self.engine.reason)
                self._stop_recorder()

    def close(self):
        with self.lock:
            try:
                self.engine.cancel(time.monotonic(), 'web service shutdown')
            finally:
                self._stop_recorder()
