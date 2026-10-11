#!/usr/bin/env python3
"""Server-side policy for releasing the software E-STOP latch from the web dashboard.

The web never releases the latch itself. After every check below passes, it asks the cmd_vel mux
through its existing /atlas/remote_stop/reset service. The mux only grants that while the physical
remote is connected and has been neutral for >= 1 s. A hardware emergency stop, if fitted, is in
the power path and is not visible to or controllable by any of this code.

Pure Python (no ROS): PIN store, failure lockout, single-use challenges, condition evaluation and an
append-only JSONL event log. CLI for the operator, run on the Jetson:
    python3 atlas_estop_reset.py set-pin      # prompts twice; stores only a salted PBKDF2 hash
    python3 atlas_estop_reset.py status
"""
import getpass, hashlib, hmac, json, os, secrets, sys, threading, time
from pathlib import Path

PIN_FILE = Path(os.environ.get('ATLAS_ESTOP_PIN_FILE', Path.home() / '.config/project_atlas/estop_reset_pin.json'))
EVENT_LOG = Path(os.environ.get('ATLAS_ESTOP_EVENT_LOG', Path.home() / 'project_atlas/data/safety/estop_events.jsonl'))
PBKDF2_ITERATIONS = 200_000
MAX_FAILURES, LOCKOUT_S = 5, 300.0
CHALLENGE_TTL_S = 10.0
CONFIRM_PHRASE = 'RESET_ESTOP'
# Conditions (all must hold at the moment of the reset request)
POLICY_MAX_AGE_S = 1.0       # fresh mux policy
JOY_MAX_AGE_S = 0.5          # physical remote connected right now
ODOM_MAX_AGE_S = 0.5         # fresh motion feedback
ODOM_MAX_VX, ODOM_MAX_WZ = 0.02, 0.05
CMD_MAX_AGE_S = 1.0          # mux output seen recently (the latch keeps publishing zero every 0.2 s)
DRIVE_QUIET_S = 1.5          # no drive request (accepted or refused) from any browser for this long
FRESH_PRESS_GAP_S = 0.5      # after a reset, a drive is accepted only after this gap in drive requests
LOG_MAX_BYTES, LOG_KEEP = 5 * 1024 * 1024, 3


def hash_pin(pin, salt, iterations=PBKDF2_ITERATIONS):
    return hashlib.pbkdf2_hmac('sha256', pin.encode(), bytes.fromhex(salt), iterations).hex()


def valid_pin_format(pin):
    return isinstance(pin, str) and pin.isdigit() and 6 <= len(pin) <= 12


class PinStore:
    def __init__(self, path=PIN_FILE):
        self.path = Path(path)

    def configured(self):
        try:
            data = json.loads(self.path.read_text())
            return bool(data.get('hash') and data.get('salt'))
        except (OSError, ValueError):
            return False

    def set(self, pin):
        if not valid_pin_format(pin):
            raise ValueError('PIN must be 6-12 digits')
        salt = secrets.token_hex(16)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix('.tmp')
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump({'salt': salt, 'iterations': PBKDF2_ITERATIONS, 'hash': hash_pin(pin, salt), 'set_at': time.time()}, f)
        os.replace(tmp, self.path); os.chmod(self.path, 0o600)

    def verify(self, pin):
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return False
        if not isinstance(pin, str) or len(pin) > 64:
            return False
        got = hash_pin(pin, data['salt'], int(data.get('iterations', PBKDF2_ITERATIONS)))
        return hmac.compare_digest(got, data['hash'])


class Lockout:
    def __init__(self, max_failures=MAX_FAILURES, lockout_s=LOCKOUT_S, clock=time.monotonic):
        self.max, self.span, self.clock = max_failures, lockout_s, clock
        self.failures, self.until, self.lock = [], 0.0, threading.Lock()

    def remaining(self):
        with self.lock:
            return max(0.0, self.until - self.clock())

    def fail(self):
        with self.lock:
            now = self.clock()
            self.failures = [t for t in self.failures if now - t < self.span] + [now]
            if len(self.failures) >= self.max:
                self.until, self.failures = now + self.span, []

    def success(self):
        with self.lock:
            self.failures = []


class Challenges:
    """Single-use, short-lived, bound to the requesting client address."""

    def __init__(self, ttl=CHALLENGE_TTL_S, clock=time.monotonic):
        self.ttl, self.clock, self.items, self.lock = ttl, clock, {}, threading.Lock()

    def issue(self, client):
        nonce = secrets.token_urlsafe(18)
        with self.lock:
            now = self.clock()
            self.items = {k: v for k, v in self.items.items() if v[1] > now}
            self.items[nonce] = (client, now + self.ttl)
        return nonce

    def consume(self, nonce, client):
        with self.lock:
            item = self.items.pop(str(nonce or ''), None)
        return bool(item) and item[0] == client and item[1] > self.clock()


def evaluate(s):
    """Return the list of reasons the reset is blocked (empty = all conditions hold).
    ``s`` is a plain dict of observations prepared by the server; missing data blocks."""
    r = []
    if not s.get('ros_ready'): r.append('ROS link not ready')
    if s.get('shutdown_pending'): r.append('shutdown in progress')
    pol, age = s.get('policy'), s.get('policy_age_s')
    if not isinstance(pol, dict) or age is None or age > POLICY_MAX_AGE_S:
        r.append('stop state unknown (mux policy stale)')
    elif pol.get('stop_latched') is not True:
        r.append('not latched')
    joy = s.get('joy_age_s')
    if joy is None or joy > JOY_MAX_AGE_S:
        r.append('physical remote not connected')
    odom, oage = s.get('odom'), s.get('odom_age_s')
    if not isinstance(odom, dict) or oage is None or oage > ODOM_MAX_AGE_S:
        r.append('motion state unknown (odometry stale)')
    elif abs(float(odom.get('vx') or 0)) > ODOM_MAX_VX or abs(float(odom.get('wz') or 0)) > ODOM_MAX_WZ:
        r.append('rover not stationary')
    cmd, cage = s.get('cmd_vel'), s.get('cmd_vel_age_s')
    if not isinstance(cmd, dict) or cage is None or cage > CMD_MAX_AGE_S:
        r.append('motor command state unknown (/cmd_vel stale)')
    elif abs(float(cmd.get('lin') or 0)) > 1e-3 or abs(float(cmd.get('ang') or 0)) > 1e-3:
        r.append('motor command not zero')
    if s.get('drive_active') or (s.get('since_drive_request_s') is not None and s['since_drive_request_s'] < DRIVE_QUIET_S):
        r.append('a drive button is still pressed (release all drive buttons)')
    if not s.get('pin_configured'): r.append('no operator PIN configured on ATLAS')
    if (s.get('lockout_s') or 0) > 0: r.append(f'too many wrong PINs; locked for {int(s["lockout_s"])} s')
    return r


class EventLog:
    def __init__(self, path=EVENT_LOG):
        self.path, self.lock = Path(path), threading.Lock()

    def write(self, event, **fields):
        fields.pop('pin', None)
        rec = {'ts': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'mono': round(time.monotonic(), 3), 'event': event, **fields}
        line = json.dumps(rec, separators=(',', ':'), default=str) + '\n'
        with self.lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                if self.path.exists() and self.path.stat().st_size > LOG_MAX_BYTES:
                    for i in range(LOG_KEEP - 1, 0, -1):
                        older = self.path.with_name(f'{self.path.name}.{i}')
                        if older.exists():
                            older.replace(self.path.with_name(f'{self.path.name}.{i + 1}'))
                    self.path.replace(self.path.with_name(self.path.name + '.1'))
                with open(self.path, 'a', encoding='utf-8') as f:
                    f.write(line)
            except OSError:
                pass   # logging must never block a stop


def _cli():
    store = PinStore()
    if len(sys.argv) > 1 and sys.argv[1] == 'set-pin':
        a = getpass.getpass('New E-STOP reset PIN (6-12 digits): '); b = getpass.getpass('Repeat: ')
        if a != b: sys.exit('PINs differ; nothing changed')
        store.set(a); EventLog().write('pin_changed', source='cli')
        print(f'PIN stored as a salted hash in {store.path} (mode 0600)')
    elif len(sys.argv) > 1 and sys.argv[1] == 'status':
        print('PIN configured' if store.configured() else 'no PIN configured'); print('event log:', EVENT_LOG)
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    _cli()
