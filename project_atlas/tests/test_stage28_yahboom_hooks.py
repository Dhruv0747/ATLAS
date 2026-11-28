"""Stage 28 (proposal): yahboom_base hook insertion, safety scope, and the CH340 identity correction."""
import ast
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'deploy' / 'stage28_yahboom_rc'))
import insert_rc_hooks          # noqa: E402
import harden_yahboom_port      # noqa: E402

BASE = (ROOT / 'scripts' / 'yahboom_base.py').read_text(encoding='utf-8')
FORBIDDEN = ('create_subscription', 'cmd_vel', 'set_car_motion', 'set_motor', 'set_akm', 'set_pwm_servo',
             'estop', 'e_stop', '/joy', '_cal_joy', 'remote_stop', 'mixer', 'Twist', 'set_car_run',
             'reset_car_state', 'write(')


def _added(before, after):
    import difflib
    return '\n'.join(l[2:] for l in difflib.ndiff(before.splitlines(), after.splitlines()) if l.startswith('+ '))


def test_hook_insert_is_additive_publish_only():
    out = insert_rc_hooks.patch(BASE)
    compile(out, 'yahboom_base.py', 'exec')
    import difflib
    assert not [l for l in difflib.ndiff(BASE.splitlines(), out.splitlines()) if l.startswith('- ')]
    added = _added(BASE, out)
    assert added.count('create_publisher(') == 1 and "'/atlas/rc/frames'" in added
    assert added.count('create_timer(') == 1
    for word in FORBIDDEN:
        assert word not in added, word
    with pytest.raises(SystemExit):
        insert_rc_hooks.patch(out)


def test_hook_keeps_existing_timers_and_motor_keepalive_first():
    out = insert_rc_hooks.patch(BASE)
    timers = re.findall(r'self\.create_timer\(([^,]+), self\.(\w+)\)', out)
    names = [n for _, n in timers]
    assert names[:4] == ['_motor_keepalive', '_publish_board_state', '_publish_battery', '_systemd_watchdog']
    assert dict((n, p) for p, n in timers)['_forward_rc_report'].strip() == '0.1'


def test_hook_can_be_disabled_and_survives_missing_modules():
    out = insert_rc_hooks.patch(BASE)
    assert "os.environ.get('ATLAS_RC_REPORT', '1') != '0'" in out
    assert "hasattr(self.bot, 'get_rc_sbus_report')" in out
    assert '_RcFrameForwarder = _RcReportForwarder = None' in out


def test_decoder_module_is_read_only():
    src = (ROOT / 'scripts' / 'atlas_yahboom_rc_report.py').read_text(encoding='utf-8')
    tree = ast.parse(src)
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | \
            {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    for bad in ('create_publisher', 'create_subscription', 'Serial', 'write', 'set_car_motion', 'rclpy'):
        assert bad not in names, bad


def test_flysky_drive_still_disabled():
    src = (ROOT / 'scripts' / 'atlas_remote_arbiter_model.py').read_text(encoding='utf-8')
    assert re.search(r'^FLYSKY_DRIVE_ENABLED\s*=\s*False\b', src, re.M)


# ------------------------------------------------------------------ USB identity
def _resolver(text, existing, env=None):
    tree = ast.parse(text)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'resolve_yahboom_port')
    const = next(n for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') == 'YAHBOOM_USB_ID')

    class FakePath:
        def __init__(self, p):
            self.p = str(p)

        def exists(self):
            return self.p in existing

        def is_dir(self):
            return self.p == '/dev/serial/by-id'

        def glob(self, pat):
            return [FakePath(x) for x in sorted(existing) if x.startswith('/dev/serial/by-id/usb-1a86_USB_Serial')]

        def __str__(self):
            return self.p

    class FakeOs:
        environ = env or {}

    ns = {'Path': FakePath, 'os': FakeOs}
    exec(compile(ast.Module(body=[const, fn], type_ignores=[]), 'x', 'exec'), ns)
    return ns['resolve_yahboom_port']


GENERIC = '/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0'   # measured: -> ttyUSB1 (GPS)


def test_current_fallback_would_pick_the_gps_link():
    assert _resolver(BASE, {GENERIC})() == GENERIC


def test_hardened_fallback_refuses_ambiguous_names():
    hard = harden_yahboom_port.patch(BASE)
    compile(hard, 'yahboom_base.py', 'exec')
    with pytest.raises(RuntimeError, match='not found'):
        _resolver(hard, {GENERIC, '/dev/yahboom'})()
    assert _resolver(hard, {GENERIC, '/dev/atlas-yahboom'})() == '/dev/atlas-yahboom'
    assert _resolver(hard, {'/dev/ttyUSB0'}, {'ATLAS_YAHBOOM_PORT': '/dev/ttyUSB0'})() == '/dev/ttyUSB0'
    with pytest.raises(RuntimeError, match='no fallback'):
        _resolver(hard, {GENERIC}, {'ATLAS_YAHBOOM_PORT': '/dev/ttyUSB9'})()
    with pytest.raises(SystemExit):
        harden_yahboom_port.patch(hard)


# measured on the Jetson 2026-10-27 (udevadm info -q property)
DEVICES = {
    'ttyUSB0 (Yahboom)': {'ID_PATH': 'platform-3610000.usb-usb-0:2.2.3:1.0', 'ID_SERIAL': '1a86_USB_Serial',
                          'idVendor': '1a86', 'idProduct': '7523'},
    'ttyUSB1 (GPS)': {'ID_PATH': 'platform-3610000.usb-usb-0:2.4.2:1.0', 'ID_SERIAL': '1a86_USB_Serial',
                      'idVendor': '1a86', 'idProduct': '7523'},
    'ttyUSB2 (IM10A IMU)': {'ID_PATH': 'platform-3610000.usb-usb-0:2.4.3:1.0', 'ID_SERIAL': '1a86_USB_Serial',
                            'idVendor': '1a86', 'idProduct': '7523'},
    'ttyUSB3 (RPLIDAR CP2102)': {'ID_PATH': 'platform-3610000.usb-usb-0:2.2.1:1.0',
                                 'ID_SERIAL': 'Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001',
                                 'idVendor': '10c4', 'idProduct': 'ea60'},
}
INSTALLED_RULE = ('SUBSYSTEM=="tty", ENV{ID_PATH}=="platform-3610000.usb-usb-0:2.2:1.0", ATTRS{idVendor}=="1a86", '
                  'ATTRS{idProduct}=="7523", SYMLINK+="atlas-yahboom", GROUP="dialout", MODE="0660"')


def _matches(rule_text):
    rules = [l for l in rule_text.splitlines() if l.strip() and not l.lstrip().startswith('#')]
    hits = {}
    for name, props in DEVICES.items():
        for rule in rules:
            conds = re.findall(r'(ENV\{(\w+)\}|ATTRS\{(\w+)\}|SUBSYSTEM)=="([^"]*)"', rule)
            ok = all(v == 'tty' if k == 'SUBSYSTEM' else props.get(e or a) == v for k, e, a, v in conds)
            if ok:
                hits[name] = re.search(r'SYMLINK\+="([^"]+)"', rule).group(1).split()
    return hits


def test_udev_rules_identity():
    assert _matches(INSTALLED_RULE) == {}                       # stale hub path: no link today
    repo_rule = (ROOT / 'udev' / '99-atlas-ch340-ports.rules').read_text()
    assert set(_matches(repo_rule)) == {'ttyUSB0 (Yahboom)', 'ttyUSB1 (GPS)', 'ttyUSB2 (IM10A IMU)'}  # ambiguous
    proposed = (ROOT / 'udev' / '99-atlas-ch340-ports.rules.stage28-proposed').read_text()
    assert _matches(proposed) == {'ttyUSB0 (Yahboom)': ['atlas-yahboom']}


def test_forward_method_publishes_new_frames_and_never_raises():
    sys.path.insert(0, str(ROOT / 'scripts'))
    import json
    import time
    import atlas_flysky_core as core
    import atlas_yahboom_rc_report as rc
    from atlas_rc_readonly_bridge import FrameForwarder
    out = insert_rc_hooks.patch(BASE)
    cls = next(n for n in ast.parse(out).body if isinstance(n, ast.ClassDef) and n.name == 'YahboomBase')
    fns = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in ('_forward_rc_report', '_publish_rc_frame')]
    ns = {'time': time, 'json': json}

    class String:
        data = ''
    ns['String'] = String
    exec(compile(ast.Module(body=fns, type_ignores=[]), 'hooks', 'exec'), ns)

    class Log:
        def __init__(self):
            self.errors, self.warnings = [], []

        def error(self, m):
            self.errors.append(m)

        def warning(self, m, **k):
            self.warnings.append(m)

    class Pub:
        def __init__(self):
            self.msgs = []

        def publish(self, m):
            self.msgs.append(json.loads(m.data))

    class Bot:
        report = None

        def get_rc_sbus_report(self):
            return self.report

    class Node:
        pass

    node = Node()
    node.bot, node._pub_rc_frames, node._rc_last_stamp = Bot(), Pub(), None
    node._rc_forwarder = rc.RcReportForwarder(FrameForwarder('sbus'))
    log = Log()
    node.get_logger = lambda: log
    node._publish_rc_frame = lambda m: ns['_publish_rc_frame'](node, m)
    fwd = lambda: ns['_forward_rc_report'](node)

    fwd()                                                    # old firmware: nothing
    assert node._pub_rc_frames.msgs == []
    f = core.encode_sbus([1000] * 16)
    for i in range(5):
        node.bot.report = (rc.build_packet(f, i, 10)[4:-1], 10.0 + 0.1 * i, i + 1)
        fwd()
        fwd()                                                # same stamp twice: no duplicate
    assert len(node._pub_rc_frames.msgs) == 5
    assert all(m['src'] == 'yahboom' and m['proto'] == 'sbus' for m in node._pub_rc_frames.msgs)
    node.bot.report = (rc.build_packet(f, 9, 10, drive_disabled=False)[4:-1], 20.0, 9)
    fwd()
    assert len(node._pub_rc_frames.msgs) == 5 and len(log.errors) == 1
    node.bot.get_rc_sbus_report = lambda: (_ for _ in ()).throw(RuntimeError('boom'))
    fwd()                                                    # swallowed, logged
    assert log.warnings
