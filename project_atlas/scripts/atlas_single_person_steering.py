"""Bounded Stage 17B scheduler. Sends only requests to the existing PWM owner.

No serial, traction, calibration-save or stop-release interface exists here.
An explicitly delegated server session survives phone-app backgrounding. The
server-to-owner lease and fresh local safety observations remain mandatory.
"""
import math
import uuid

PLAN = (90, 95, 100, 95, 90, 85, 80, 85, 90)
TERMINAL = ('IDLE', 'COMPLETE', 'CANCELLED')


def caliper_angle(delta_y_mm, baseline_mm, error_mm=1.0):
    """Two points on the rigid wheel axis, separated by measured distance L.

    Delta-y is their signed lateral offset difference against a chassis-fixed
    forward reference. L is point-to-point distance, not projected distance.
    Error includes both offset readings and baseline placement conservatively.
    """
    d, length, error = map(float, (delta_y_mm, baseline_mm, error_mm))
    if not all(math.isfinite(x) for x in (d, length, error)) or not 40 <= length <= 150 or not 0 < error <= 5:
        raise ValueError('measured 40..150 mm rigid baseline and positive uncertainty required')
    if abs(d) + 2*error >= length-error:
        raise ValueError('offset/reference geometry too uncertain')
    angle = math.degrees(math.asin(d/length))
    bounds = [math.degrees(math.asin((d+s*2*error)/(length+t*error)))
              for s in (-1, 1) for t in (-1, 1)]
    return angle, max(abs(b-angle) for b in bounds)


def measurement_report(readings, method, uncertainty_deg=2.0, baselines=None, error_mm=1.0):
    if method not in ('visual_protractor', 'caliper'):
        raise ValueError('phone tilt/orientation cannot measure road-wheel deflection')
    if not isinstance(readings, list) or len(readings) != len(PLAN) or any(not isinstance(row, dict) for row in readings):
        raise ValueError('one reading row per held position required')
    if baselines is not None and not isinstance(baselines, dict):
        raise ValueError('per-wheel baseline mapping required')
    result = {'method': method, 'calibration_written': False, 'wheels': {}}
    for wheel in ('front_left', 'front_right'):
        angles, bounds = [], []
        for row in readings:
            value = row.get(wheel)
            if value is None:
                angles.append(None); bounds.append(None); continue
            if method == 'caliper':
                angle, bound = caliper_angle(value, (baselines or {}).get(wheel), error_mm)
            else:
                angle, bound = float(value), float(uncertainty_deg)
                if not math.isfinite(angle) or not -180 <= angle <= 180 or not 0 < bound <= 10:
                    raise ValueError('finite visual angle and explicit uncertainty required')
            angles.append(angle); bounds.append(bound)
        if angles[0] is None:
            result['wheels'][wheel] = {'valid': False, 'reason': 'initial measured centre missing'}
            continue
        centre = angles[0]
        deflection = [None if a is None else round(a-centre, 3) for a in angles]
        uncertainty = [None if b is None else round(b+bounds[0], 3) for b in bounds]
        hysteresis = {str(PLAN[a]): None if angles[a] is None or angles[b] is None else round(angles[b]-angles[a], 3)
                      for a, b in ((1, 3), (5, 7))}
        linearity = {}
        for label, halfway, extreme in (('left', 1, 2), ('right', 5, 6)):
            linearity[label] = None if angles[halfway] is None or angles[extreme] is None else {
                'second_difference_deg': round(angles[extreme]-2*angles[halfway]+centre, 3),
                'bound_deg': round(bounds[extreme]+2*bounds[halfway]+bounds[0], 3)}
        result['wheels'][wheel] = {'valid': True, 'centre_reference_deg': centre,
            'deflection_deg': deflection, 'deflection_bound_deg': uncertainty,
            'return_minus_outward_deg': hysteresis,
            'centre_return_deg': [deflection[i] for i in (0, 4, 8)],
            'left_10_vs_right_10_deg': [deflection[2], deflection[6]],
            'nonlinearity_comparison': linearity,
            'limitations': 'Visual/caliper geometry estimate; chassis reference, tyre flex and placement errors may exceed stated bound.'}
    return result


class SinglePersonSteering:
    def __init__(self, send, stop, emit=lambda event: None, announce=lambda text: None, *, enabled=False):
        self.send, self.stop, self.emit, self.announce = send, stop, emit, announce
        self.enabled = enabled
        self.state = 'IDLE'
        self.client = None
        self.owner_session = None
        self.sequence = 0
        self.events = []
        self.step = 0
        self.due = 0.0
        self.deadline = 0.0
        self.last_heartbeat = -1e9
        self.pending_seq = -1
        self.settled_since = None
        self.resume_state = None
        self.resume_remaining = 0.0
        self.measurements = None
        self.reason = ''
        self.last_tick = None

    def event(self, name, now, **data):
        item = {'event': name, 'test_id': self.owner_session, 'monotonic_s': now, 'state': self.state,
                'step': self.step+1, 'command_pwm_deg': PLAN[self.step], **data}
        self.events.append(item)
        self.events = self.events[-128:]
        self.emit(item)

    def request(self, op, now, **data):
        self.sequence += 1
        command = dict(op=op, session=self.owner_session, seq=self.sequence, **data)
        self.send(command)
        self.last_heartbeat = now
        return self.sequence

    def problem(self, snapshot, owned=False, recording=True):
        if snapshot.get('shutdown') or snapshot.get('safe') is not True:
            return snapshot.get('problem') or 'fresh safety/zero-traction evidence unavailable'
        owner = snapshot.get('owner') or {}
        if owner.get('saved', {}).get('front', {}).get('center') != 90:
            return 'fixed test requires existing saved front centre 90; no calibration change permitted'
        if snapshot.get('rear_applied') != owner.get('saved', {}).get('rear', {}).get('center'):
            return 'rear must already be at its saved centre; no rear movement allowed'
        if owned and (owner.get('session') != self.owner_session or not owner.get('locked') or not owner.get('lease_active')):
            return 'steering-owner lease lost'
        if owned and (owner.get('traction_inhibited') is not True or type(owner.get('sequence_ack')) is not int):
            return 'steering-only interlock/acknowledgement unavailable'
        if recording and snapshot.get('recorder_ready') is not True:
            return 'Stage 17 recorder unavailable/stale'
        return ''

    def prepare(self, client, now, snapshot, confirmations, mode='caliper'):
        if not self.enabled:
            raise ValueError('Stage 17B disabled pending reviewed deployment approval')
        if self.state not in TERMINAL:
            raise ValueError('a bounded test already owns the controls')
        if mode not in ('caliper', 'observe') or not isinstance(client, str) or len(client) != 32:
            raise ValueError('valid client and measurement mode required')
        if not isinstance(confirmations, dict) or any(confirmations.get(k) is not True for k in ('lifted', 'charger_disconnected', 'hands_clear', 'cutoff_ready')):
            raise ValueError('lifted wheels, charger disconnected, hands clear and cutoff confirmation required')
        problem = self.problem(snapshot, recording=False)
        owner = snapshot.get('owner') or {}
        if problem or owner.get('locked') or snapshot.get('front_applied') != 90:
            raise ValueError(problem or 'steering must already be centred and unowned')
        self.client, self.owner_session = client, uuid.uuid4().hex
        self.sequence, self.events, self.step = 0, [], 0
        self.mode, self.reason, self.measurements = mode, '', None
        self.deadline, self.state = now+60, 'PREPARING'
        self.last_tick = now
        self.event('prepare', now, mode=mode, maximum_seconds=300 if mode == 'caliper' else 210)

    def authorize(self, client):
        if client != self.client:
            raise ValueError('this browser does not own the prepared test')

    def start(self, client, now, snapshot, approved=False, return_center=False):
        self.authorize(client)
        if self.state != 'READY' or now >= self.deadline or not approved or not return_center:
            raise ValueError('READY, explicit bounded-sequence approval and planned centre-return permission required')
        problem = self.problem(snapshot, owned=True)
        if problem:
            raise ValueError(problem)
        self.state, self.due = 'COUNTDOWN', now+10
        self.deadline = now+(300 if self.mode == 'caliper' else 210)
        self.event('start_authorized', now, phone_background_policy='bounded server delegation; owner link must stay live')
        self.announce('Front steering test starts in ten seconds. Keep hands clear.')

    def cancel(self, now, reason='operator cancel'):
        if self.state in TERMINAL:
            return
        self.state, self.reason = 'CANCELLED', reason
        self.stop(reason)  # Existing stop-only input freezes the existing owner.
        self.event('cancel', now, reason=reason, return_to_centre=False)
        self.announce('Steering test cancelled. No automatic return to centre.')

    def emergency(self, now):
        if self.state in TERMINAL:
            self.stop('Stage 17B emergency stop')
        else:
            self.cancel(now, 'Stage 17B emergency stop')

    def pause(self, client, now):
        self.authorize(client)
        if self.state not in ('COUNTDOWN', 'HOLD', 'SETTLING'):
            raise ValueError('test is not advancing')
        self.resume_state = self.state
        self.resume_remaining = max(0, self.due-now)
        self.state = 'PAUSED'
        self.event('pause_future_steps', now)
        self.announce('Future steps paused. Wait until the wheel is visibly still before measuring.')

    def resume(self, client, now, hands_clear=False):
        self.authorize(client)
        if self.state != 'PAUSED' or not hands_clear:
            raise ValueError('paused state and hands-clear confirmation required')
        if self.resume_state == 'NEXT':
            self.step += 1
            self.state, self.due = 'COUNTDOWN', now+3
        else:
            self.state, self.due = self.resume_state, now+self.resume_remaining
        self.event('resume', now)
        self.announce('Hands clear. Next steering step is counting down.')

    def tick(self, now, snapshot):
        if self.state in TERMINAL:
            return
        if self.last_tick is not None and (now < self.last_tick or now-self.last_tick > .75):
            self.cancel(now, 'supervisor timing/communication gap')
            return
        self.last_tick = now
        if now >= self.deadline:
            self.cancel(now, 'maximum duration/prepare timeout')
            return
        problem = self.problem(snapshot, owned=self.state not in ('PREPARING', 'ACQUIRING'),
                               recording=self.state != 'PREPARING')
        if problem:
            self.cancel(now, problem)
            return
        owner = snapshot['owner']
        if self.state == 'PREPARING':
            if snapshot.get('recorder_ready'):
                self.pending_seq = self.request('enter', now, lifted=True)
                self.state, self.due = 'ACQUIRING', now+2
                self.event('owner_enter_requested', now)
            return
        if self.state == 'ACQUIRING':
            if owner.get('session') == self.owner_session and owner.get('lease_active') and owner.get('locked'):
                self.state = 'READY'; self.event('ready', now)
            elif now > self.due:
                self.cancel(now, 'steering-owner acknowledgement timeout')
            return
        if now-self.last_heartbeat >= .35:
            self.request('heartbeat', now)
        if self.state == 'COUNTDOWN' and now >= self.due:
            difference = PLAN[self.step]-owner['targets']['front']
            if difference not in (-5, 0, 5):
                self.cancel(now, 'unexpected current target; no catch-up sweep')
                return
            if difference:
                self.pending_seq = self.request('jog', now, side='front', step=difference)
            self.state, self.due, self.settled_since = 'SETTLING', now+3, None
            self.event('command', now, owner_sequence=self.pending_seq, rear_unchanged=True)
            self.announce(f'Step {self.step+1}. Command {PLAN[self.step]}. Keep hands clear.')
        elif self.state == 'SETTLING':
            ack = owner.get('sequence_ack', -1) >= self.pending_seq
            reached = snapshot.get('front_applied') == PLAN[self.step] and owner.get('targets', {}).get('front') == PLAN[self.step]
            if ack and reached:
                if self.settled_since is None:
                    self.settled_since = now
                if now-self.settled_since >= .5:
                    self.state, self.due = 'HOLD', now+15
                    self.event('hold_15_seconds', now, physical_position_feedback=False)
            else:
                self.settled_since = None
            if self.state == 'SETTLING' and now >= self.due:
                self.cancel(now, 'software command acknowledgement/settle timeout')
        elif self.state == 'HOLD' and now >= self.due:
            if self.step == len(PLAN)-1:
                self.state = 'COMPLETE'
                self.stop('Stage 17B complete; freeze saved-centre command')
                self.event('complete', now, calibration_saved=False)
                self.announce('Front steering test complete. Enter your measurements in the dashboard.')
            elif self.mode == 'caliper':
                self.state, self.resume_state = 'PAUSED', 'NEXT'
                self.event('pause_for_contact_measurement', now)
                self.announce('Paused for measurement. Press Resume only after your hands are clear.')
            else:
                self.step += 1
                self.state, self.due = 'COUNTDOWN', now+3
                self.event('next_countdown', now)
                self.announce('Next steering step in three seconds. Keep hands clear.')

    def status(self, now):
        return {'enabled': self.enabled, 'state': self.state, 'step': self.step+1,
                'test_id': self.owner_session,
                'plan_pwm_degrees': list(PLAN), 'current_command_deg': PLAN[self.step],
                'hold_seconds': 15, 'remaining_seconds': round(max(0, self.due-now), 1),
                'maximum_remaining_seconds': round(max(0, self.deadline-now), 1),
                'mode': getattr(self, 'mode', 'caliper'), 'reason': self.reason,
                'history': self.events, 'measurements': self.measurements,
                'traction_authorized': False, 'calibration_saving': False,
                'phone_policy': 'After Start, phone foreground/network is not the controlling lease. Local server-owner lease is required; maximum duration always applies.'}
