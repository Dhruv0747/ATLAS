"""Stage 28: postflight safety diagnostics of the B1 maintenance wrapper. Offline; fake HTTP, files and services.

The authoritative verdict is still atlas_b1_interlock.Interlock.safe (+ packet_counter). These tests check that
every rejection leaves a complete, redacted, hash-verified snapshot naming the failed predicate, and that no
missing/stale/malformed input can become PASS.
"""
import hashlib
import io
import json
import math
import socket
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / 'tools/diagnostics'))
sys.path.insert(0, str(ROOT / 'tools/diagnostics/stm32_readback'))
sys.path.insert(0, str(ROOT / 'scripts'))
import deploy_maintenance_once as deploy   # noqa: E402
import atlas_b1_interlock as interlock     # noqa: E402


def good_status(**over):
    policy = {'manual_only': True, 'commission_armed': False, 'commission_remaining_s': 0.0, 'stop_latched': True,
              'stop_reason': 'REMOTE STOP: joystick unavailable', 'source': 'STOPPED'}
    policy.update(over.pop('policy', {}))
    cmd = {'lin': 0.0, 'ang': 0.0}
    cmd.update(over.pop('cmd', {}))
    enc = {'state': 'READY', 'packet_age_s': 0.02, 'packet_fresh': True, 'link_state': 'LIVE',
           'serial_encoder_packets': over.pop('packets', 1000)}
    status = {'ros': {
        'control_policy': {'value': json.dumps(policy), 'age': over.pop('policy_age', 0.0), 'sample_time': 1793092434.97,
                           'source': 'web telemetry callback', 'observed_hz': 10.0},
        'cmd_vel': {'value': cmd, 'age': over.pop('cmd_age', 0.1), 'sample_time': 1793092434.92,
                    'source': 'web telemetry callback', 'observed_hz': 10.0},
        'encoder_health': {'value': json.dumps(enc), 'age': 0.0}},
        'network': {'wifi_ip': '192.168.1.16', 'tailscale_ip': '100.87.208.71', 'ssh': 'jetson@100.87.208.71'},
        'system': {'cpu_percent': 58}}
    status.update(over)
    return status


class Resp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy, 'ROOT', tmp_path)
    monkeypatch.setattr(deploy, 'gate', SimpleNamespace(safe=interlock.Interlock.safe), raising=False)
    monkeypatch.setattr(deploy, 'gate_module', interlock, raising=False)
    deploy.SAFETY_SAMPLES.clear()
    deploy.EVIDENCE.clear()
    queue = []

    def urlopen(url, timeout):
        assert url == deploy.STATUS_URL and timeout == 3
        item = queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return Resp(item if isinstance(item, bytes) else json.dumps(item).encode())
    monkeypatch.setattr(deploy.urllib.request, 'urlopen', urlopen)
    return SimpleNamespace(root=tmp_path, queue=queue)


def rejection(env, item):
    env.queue.append(item)
    with pytest.raises(deploy.SafetyRejected) as e:
        deploy.safety('postflight-1')
    rec = e.value.record
    saved = Path(rec['evidence']['path'])
    data = saved.read_bytes()
    assert hashlib.sha256(data).hexdigest() == rec['evidence']['sha256']
    on_disk = json.loads(data)
    assert on_disk['verdict'] == 'REJECT' and on_disk['phase'] == 'postflight-1'
    assert on_disk['failed_predicates'] == rec['failed_predicates']
    for k in ('request_wall', 'request_monotonic', 'response_monotonic', 'evaluated_monotonic', 'evaluation_delay_s'):
        assert k in on_disk
    samples = json.loads((env.root / 'evidence' / 'safety-samples.json').read_text())
    assert samples[-1]['verdict'] == 'REJECT'
    return rec, on_disk, str(e.value)


def test_good_snapshot_passes_and_is_recorded(env):
    env.queue.append(good_status())
    out = deploy.safety('preflight')
    assert out['packet_count'] == 1000
    rec = deploy.SAFETY_SAMPLES[-1]
    assert rec['verdict'] == 'PASS' and rec['gate_verdict'] is True and rec['failed_predicates'] == []
    assert {p['predicate'] for p in rec['predicates']} == {
        'control_policy_fresh', 'cmd_vel_fresh', 'estop_latched', 'manual_only', 'commissioning_disarmed',
        'control_source_stopped', 'zero_command'}
    assert not list((env.root / 'evidence').glob('safety-rejection-*'))


@pytest.mark.parametrize('over,predicate', [
    ({'policy': {'stop_latched': False}}, 'estop_latched'),
    ({'policy': {'stop_latched': 'true'}}, 'estop_latched'),
    ({'policy': {'manual_only': False}}, 'manual_only'),
    ({'policy': {'commission_armed': True}}, 'commissioning_disarmed'),
    ({'policy': {'source': 'XBOX'}}, 'control_source_stopped'),
    ({'cmd': {'lin': 0.05}}, 'zero_command'),
    ({'cmd': {'ang': -0.2}}, 'zero_command'),
    ({'cmd': {'lin': True}}, 'zero_command'),
    ({'cmd': {'lin': None}}, 'zero_command'),
    ({'policy_age': 1.5}, 'control_policy_fresh'),
    ({'cmd_age': 1.01}, 'cmd_vel_fresh'),
    ({'cmd_age': None}, 'cmd_vel_fresh'),
    ({'policy_age': -0.1}, 'control_policy_fresh'),
    ({'cmd_age': float('nan')}, 'cmd_vel_fresh'),
    ({'cmd_age': float('inf')}, 'cmd_vel_fresh'),
])
def test_each_condition_is_named_with_raw_observation(env, over, predicate):
    rec, saved, message = rejection(env, good_status(**over))
    assert rec['failed_predicates'] == [predicate], rec['failed_predicates']
    failed = [p for p in saved['predicates'] if not p['pass']]
    assert failed[0]['predicate'] == predicate and failed[0]['reason'] and failed[0]['observed'] is not None
    assert predicate in message and rec['gate_verdict'] is False


def test_missing_fields_and_unparsable_policy(env):
    s = good_status()
    del s['ros']['cmd_vel']
    rec, _, _ = rejection(env, s)
    assert 'cmd_vel_present' in rec['failed_predicates']
    s = good_status()
    s['ros']['control_policy']['value'] = '{not json'
    rec, _, _ = rejection(env, s)
    assert 'control_policy_parse' in rec['failed_predicates']
    s = good_status()
    s['ros']['control_policy']['value'] = json.dumps({'manual_only': True, 'source': 'STOPPED', 'commission_armed': False})
    rec, _, _ = rejection(env, s)
    assert rec['failed_predicates'] == ['estop_latched']
    rec, _, _ = rejection(env, {'unexpected': True})
    assert rec['failed_predicates'] == ['api_shape']


@pytest.mark.parametrize('item', [socket.timeout('timed out'), ConnectionRefusedError(111, 'refused'), b'{not json', b'',
                                  b'x' * (300 * 1024)])
def test_api_timeout_error_malformed_or_oversize(env, item):
    rec, saved, _ = rejection(env, item)
    assert rec['failed_predicates'] == ['api_available'] and saved['api_error']


def test_multiple_simultaneous_failures_all_reported(env):
    rec, saved, message = rejection(env, good_status(policy={'stop_latched': False, 'manual_only': False},
                                                     cmd={'lin': 0.3}, cmd_age=2.0))
    assert set(rec['failed_predicates']) == {'estop_latched', 'manual_only', 'zero_command', 'cmd_vel_fresh'}
    for name in rec['failed_predicates']:
        assert name in message


def test_exact_freshness_boundary_unchanged(env):
    env.queue.append(good_status(policy_age=1.0, cmd_age=1.0))
    assert deploy.safety()['packet_count'] == 1000
    rec, _, _ = rejection(env, good_status(policy_age=1.0001))
    assert rec['failed_predicates'] == ['control_policy_fresh']


def test_gate_is_authoritative_and_disagreement_is_reported(env, monkeypatch):
    monkeypatch.setattr(deploy, 'gate', SimpleNamespace(safe=lambda s: False))
    rec, _, _ = rejection(env, good_status())
    assert rec['failed_predicates'] == ['gate_consistency']
    monkeypatch.setattr(deploy, 'gate', SimpleNamespace(safe=lambda s: True))   # a broken gate cannot make a bad sample PASS
    rec, _, _ = rejection(env, good_status(policy={'stop_latched': False}))
    assert rec['failed_predicates'] == ['estop_latched']

    def boom(s):
        raise KeyError('ros')
    monkeypatch.setattr(deploy, 'gate', SimpleNamespace(safe=boom))
    rec, saved, _ = rejection(env, good_status())
    assert rec['failed_predicates'] == ['gate_consistency'] and "KeyError('ros')" in saved['gate_error']


def test_encoder_packet_rejection_is_recorded(env):
    s = good_status()
    s['ros']['encoder_health']['value'] = json.dumps({'packet_age_s': 5.0, 'packet_fresh': False, 'serial_encoder_packets': 10})
    rec, saved, message = rejection(env, s)
    assert rec['failed_predicates'] == ['encoder_packets'] and message.startswith('encoder packet evidence rejected')


def test_redaction_keeps_safety_fields(env):
    s = good_status(auth_token='tskey-auth-abcdefgh12345', challenge='xmIzb68jrOKL0jyCuq')
    s['ros']['wifi_password'] = 'hunter2'
    s['ros']['control_policy']['value'] = json.dumps({'manual_only': True, 'commission_armed': False, 'stop_latched': False,
                                                      'source': 'STOPPED'})
    rec, saved, _ = rejection(env, s)
    text = Path(rec['evidence']['path']).read_text()
    for secret in ('tskey-auth', 'xmIzb68jrOKL0jyCuq', 'hunter2', '192.168.1.16', '100.87.208.71'):
        assert secret not in text, secret
    st = saved['status_redacted']
    assert json.loads(st['ros']['control_policy']['value'])['stop_latched'] is False
    assert st['ros']['cmd_vel']['value'] == {'lin': 0.0, 'ang': 0.0}
    assert st['network']['wifi_ip'] == '[REDACTED-IPV4]'


def test_snapshot_write_failure_still_rejects_and_says_so(env, monkeypatch):
    def fail(*a):
        raise OSError(28, 'No space left on device')
    monkeypatch.setattr(deploy, 'write_evidence', fail)
    env.queue.append(good_status(policy={'stop_latched': False}))
    with pytest.raises(deploy.SafetyRejected) as e:
        deploy.safety('postflight-1')
    assert 'EVIDENCE NOT SAVED' in str(e.value) and 'No space' in e.value.record['evidence_error']
    env.queue.append(good_status())          # a PASS that cannot be evidenced is not a PASS
    with pytest.raises(deploy.EvidenceError):
        deploy.safety('postflight-2')


def test_evidence_write_is_atomic_and_verified(env, monkeypatch):
    entry = deploy.write_evidence('x.json', {'a': 1})
    assert hashlib.sha256(Path(entry['path']).read_bytes()).hexdigest() == entry['sha256']
    real = deploy.os.replace

    def broken_replace(src, dst):
        Path(dst).write_bytes(b'corrupt')      # simulate a torn/foreign write landing at the target
    monkeypatch.setattr(deploy.os, 'replace', broken_replace)
    with pytest.raises(deploy.EvidenceError):
        deploy.write_evidence('y.json', {'b': 2})
    monkeypatch.setattr(deploy.os, 'replace', real)
    assert sorted(p.name for p in (env.root / 'evidence').iterdir()) == ['x.json', 'y.json']   # no temp files left


# ------------------------------------------------------------------ full transaction: postflight rejection -> rollback
def test_postflight_rejection_rolls_back_and_keeps_evidence(tmp_path, monkeypatch):
    stage = tmp_path / 'stage'; stage.mkdir()
    scripts = tmp_path / 'scripts'; scripts.mkdir()
    units = tmp_path / 'units'; units.mkdir()
    dropdir = units / 'rover-base-telemetry.service.d'; dropdir.mkdir()
    (dropdir / 'priority.conf').write_bytes(b'original priority')
    recovery = scripts / 'atlas_sensor_recovery.py'; recovery.write_bytes(b'original recovery')
    base = units / 'rover-base-telemetry.service'; base.write_bytes(b'original base')
    state = tmp_path / 'state'
    before = {str(x): hashlib.sha256(x.read_bytes()).hexdigest() for x in [recovery, base, dropdir / 'priority.conf']}
    for key, value in {'ROOT': stage, 'S': scripts, 'U': units, 'STATE': state, 'DROP': dropdir / '98-b1-maintenance.conf',
                       'BACK': stage / 'rollback', 'C': stage / 'candidate', 'EXPECTED': before, 'modified': False,
                       'trace': [], 'result': {'status': 'PREFLIGHT'}}.items():
        monkeypatch.setattr(deploy, key, value)
    deploy.SAFETY_SAMPLES.clear(); deploy.EVIDENCE.clear()
    content = {'atlas_b1_interlock.py': b'fake module', 'atlas_sensor_recovery.py': b'candidate recovery',
               'b1-maintenance.conf': b'candidate condition'}
    content['SHA256.json'] = json.dumps({n: hashlib.sha256(b).hexdigest() for n, b in content.items()}).encode()
    with tarfile.open(stage / 'candidate.tar', 'w') as t:
        for n, b in content.items():
            info = tarfile.TarInfo(n); info.size = len(b); t.addfile(info, io.BytesIO(b))
    (stage / 'baseline-backup.tar').write_bytes(b'fake baseline archive')
    realsha = deploy.sha
    monkeypatch.setattr(deploy, 'sha', lambda p: {
        'candidate.tar': 'a28c5ea60de2b9276a2a275d1c2bb0bd303d959a61821b7f0217dc05a428a756',
        'baseline-backup.tar': '6f583eb097236eb675986d472b7ece3c74722a051f1867a58e0b98fed2bda87a'}.get(Path(p).name) or realsha(p))

    class Gate:
        safe = staticmethod(interlock.Interlock.safe)

        def initialize(self):
            state.mkdir(); (state / 'state.json').write_text('{"version":1,"phase":"IDLE"}')

        def start_gate(self):
            return True

        def load(self):
            return json.loads((state / 'state.json').read_text())
    fake = SimpleNamespace(Interlock=Gate, no_base_jobs=lambda: True, packet_counter=interlock.packet_counter)
    monkeypatch.setattr(deploy.importlib.util, 'spec_from_file_location', lambda *a: SimpleNamespace(loader=SimpleNamespace(exec_module=lambda m: None)))
    monkeypatch.setattr(deploy.importlib.util, 'module_from_spec', lambda s: fake)
    calls = []; restarts = [0]

    def cmd(*a):
        calls.append(a)
        if 'restart' in a:
            assert a == ('systemctl', '--user', 'restart', 'atlas-sensor-recovery.service')
            restarts[0] += 1
        if 'ExecCondition' in a:
            return str(scripts / 'atlas_b1_interlock.py')
        return 'READY: full bounded fault recovery armed'
    monkeypatch.setattr(deploy, 'cmd', cmd)
    monkeypatch.setattr(deploy, 'stats', lambda: {n: {'Id': n, 'ActiveState': 'active', 'NRestarts': '0',
        'MainPID': str(100 + restarts[0] if n == 'atlas-sensor-recovery.service' else 20)} for n in deploy.UNITS})
    monkeypatch.setattr(deploy, 'resource', lambda: {'cpu_pct': 30, 'ram_pct': 40, 'temp_c': 59})
    monkeypatch.setattr(deploy.time, 'sleep', lambda _: None)
    # preflight + pre-write PASS; first postflight sample: stale command telemetry right after the recovery restart
    feed = [good_status(packets=1000), good_status(packets=1010), good_status(packets=1020, cmd_age=1.4)]
    monkeypatch.setattr(deploy.urllib.request, 'urlopen', lambda url, timeout: Resp(json.dumps(feed.pop(0)).encode()))

    result = deploy.deploy()

    assert result['status'] == 'ROLLED_BACK', result.get('error')
    assert not any('rover-base-telemetry.service' in c and 'restart' in c for c in calls)
    for name, digest in before.items():
        assert realsha(name) == digest
    assert not deploy.DROP.exists() and not (scripts / 'atlas_b1_interlock.py').exists()
    rej = result['safety_rejection']
    assert rej['phase'] == 'postflight-1' and rej['failed_predicates'] == ['cmd_vel_fresh']
    assert rej['predicates'][0]['observed']['age'] == 1.4
    ev = Path(rej['evidence']['path'])
    assert ev.exists() and hashlib.sha256(ev.read_bytes()).hexdigest() == rej['evidence']['sha256']
    assert [s['verdict'] for s in result['safety_samples']] == ['PASS', 'PASS', 'REJECT']
    on_disk = json.loads((stage / 'result.json').read_text())
    assert on_disk['safety_rejection']['failed_predicates'] == ['cmd_vel_fresh']
    assert {e['path'] for e in on_disk['evidence']} >= {str(ev), str(stage / 'evidence' / 'safety-samples.json')}


def test_cli_refuses_staging_with_previous_evidence(tmp_path, monkeypatch):
    (tmp_path / 'evidence').mkdir()
    monkeypatch.setattr(sys, 'argv', ['deploy', '--staging', str(tmp_path), '--approve-maintenance-install'])
    monkeypatch.setattr(deploy, 'deploy', lambda: pytest.fail('deployment executed'))
    with pytest.raises(SystemExit):
        deploy.main()


def test_redaction_does_not_touch_times_or_numbers():
    v = deploy.redact({'stop_reason': 'REMOTE STOP 14:43:58', 'x': 0.3, 'ipv6': 'fe80::1', 'mac': 'aa:bb:cc:dd:ee:ff'})
    assert v['stop_reason'] == 'REMOTE STOP 14:43:58' and v['x'] == 0.3
    assert v['ipv6'] == '[REDACTED-IPV6]' and v['mac'] == '[REDACTED-IPV6]'
