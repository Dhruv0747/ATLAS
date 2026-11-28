"""Stage 28 (proposal): ATLAS-patched Yahboom firmware RC report -> Jetson -> FlySky Test Lab. Offline only."""
import ctypes
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tools' / 'deploy' / 'stage28_yahboom_rc'))

import atlas_flysky_core as core                      # noqa: E402
import atlas_yahboom_rc_report as rc                  # noqa: E402
from atlas_rc_readonly_bridge import FrameForwarder   # noqa: E402
import atlas_usb_identity                             # noqa: E402
import insert_rosmaster_rc                            # noqa: E402

PATCH = ROOT / 'firmware' / 'yahboom_rc_report' / 'atlas_rc_report.patch'


def frame(channels=None, lost=False, failsafe=False):
    ch = channels or [992 + 10 * i for i in range(16)]
    return core.encode_sbus(ch, frame_lost=lost, failsafe=failsafe)


def packet_checksum_ok(pkt):
    return sum(pkt[2:-1]) & 0xFF == pkt[-1]


# ------------------------------------------------------------------ packet format
def test_round_trip_all_16_channels_and_flags():
    ch = [random.Random(i).randrange(172, 1812) for i in range(16)]
    for lost, fs in ((False, False), (True, False), (False, True)):
        pkt = rc.build_packet(frame(ch, lost, fs), seq=7, age_ms=30)
        assert len(pkt) == rc.PACKET_LEN and pkt[:4] == bytes([0xFF, 0xFB, 0x1E, 0xE1]) and packet_checksum_ok(pkt)
        r = rc.parse_payload(pkt[4:-1])
        assert r.seq == 7 and r.ever and r.fresh and r.drive_disabled and r.age_ms == 30
        assert (r.frame_lost, r.failsafe) == (lost, fs)
        f = core.decode_sbus(r.sbus_frame)
        assert list(f.raw) == ch and (f.frame_lost, f.failsafe) == (lost, fs)


def test_never_received_and_stale_and_saturated_age():
    r = rc.parse_payload(rc.build_packet(None, 0, None)[4:-1])
    assert not r.ever and r.sbus_frame is None and r.age_ms is None and not r.fresh
    r = rc.parse_payload(rc.build_packet(frame(), 3, 250)[4:-1])
    assert r.ever and not r.fresh and r.age_ms == 250
    r = rc.parse_payload(rc.build_packet(frame(), 3, 9000)[4:-1])
    assert r.age_ms is None and not r.fresh


@pytest.mark.parametrize('mutate,reason', [
    (lambda p: p[:-1], 'length'),
    (lambda p: bytes([0xA0]) + p[1:], 'format'),
])
def test_malformed_payload_rejected(mutate, reason):
    payload = rc.build_packet(frame(), 1, 10)[4:-1]
    with pytest.raises(rc.ReportRejected, match=reason):
        rc.parse_payload(mutate(payload))


def test_drive_enabled_firmware_is_refused():
    payload = rc.build_packet(frame(), 1, 10, drive_disabled=False)[4:-1]
    with pytest.raises(rc.ReportRejected, match='drive ENABLED'):
        rc.parse_payload(payload)
    fwd = rc.RcReportForwarder(FrameForwarder('sbus'))
    out = []
    assert fwd.handle(payload, 1.0, 1.0, out.append) == 0 and not out
    assert fwd.status()['drive_enabled_firmware_seen'] is True


# ------------------------------------------------------------------ firmware C code == Python mirror
def _firmware_builder_source():
    text = PATCH.read_bytes().decode('utf-8', 'replace').replace('\r', '')
    added = '\n'.join(l[1:] for l in text.split('\n') if l.startswith('+') and not l.startswith('+++'))
    m = re.search(r'(uint8_t SBUS_Build_Report\(.*?\n\}\n)', added, re.S)
    assert m, 'SBUS_Build_Report not found in patch'
    defs = dict(re.findall(r'#define (SBUS_\w+)\s+(\([^)]*\)|\S+)', added))
    return m.group(1), defs


@pytest.mark.skipif(shutil.which('cc') is None, reason='needs a host C compiler')
def test_firmware_report_builder_matches_python_mirror(tmp_path):
    body, defs = _firmware_builder_source()
    hdr = ''.join('#define %s %s\n' % (k, v) for k, v in defs.items() if k.startswith('SBUS_'))
    src = tmp_path / 'r.c'
    src.write_text('#include <stdint.h>\n#define PTO_HEAD 0xFF\n#define PTO_DEVICE_ID 0xFC\n'
                   '#define FUNC_REPORT_RC_SBUS 0xE1\n' + hdr + body)
    lib = tmp_path / 'r.so'
    subprocess.run(['cc', '-shared', '-fPIC', '-O2', str(src), '-o', str(lib)], check=True)
    so = ctypes.CDLL(str(lib))
    so.SBUS_Build_Report.restype = ctypes.c_uint8
    rnd = random.Random(28)
    for i in range(400):
        ever = i % 9 != 0
        f = frame([rnd.randrange(0, 2048) for _ in range(16)], rnd.random() < .2, rnd.random() < .2)
        age = rnd.choice([0, 9, 10, 99, 100, 101, 2549, 2550, 5000, 70000])
        seq = rnd.randrange(256)
        out = (ctypes.c_uint8 * 32)()
        n = so.SBUS_Build_Report(out, (ctypes.c_uint8 * 25)(*f), ctypes.c_uint8(seq), ctypes.c_uint8(ever),
                                 ctypes.c_uint32(age))
        assert n == 32
        assert bytes(out) == rc.build_packet(f if ever else None, seq, age if ever else None), (i, age)


def test_patch_compiles_drive_out_and_keeps_vendor_parser():
    text = PATCH.read_bytes().decode('utf-8', 'replace')
    assert '+#define ENABLE_SBUS_DRIVE            0' in text
    assert '+        #elif ENABLE_SBUS_DRIVE' in text and '-        #else' in text
    assert '+#define ALL_CHANNELS ' in text
    assert '0xE1' in text and 'FUNC_REPORT_RC_SBUS' in text
    removed = [l for l in text.replace('\r', '').split('\n') if l.startswith('-') and not l.startswith('---')]
    # only two vendor lines change: the drive #else and the version patch number
    assert len(removed) == 2, removed
    for word in ('Motion_', 'Ackerman_Ctrl', 'Mecanum_Ctrl', 'Fourwheel_Ctrl', 'Motor_'):
        assert not [l for l in text.split('\n') if l.startswith('+') and word in l], word


# ------------------------------------------------------------------ Rosmaster_Lib compatibility
class _FakeSerial:
    def __init__(self, data):
        self.data, self.i = bytes(data), 0

    def read(self, n=1):
        if self.i >= len(self.data):
            raise EOFError
        b = self.data[self.i:self.i + n]
        self.i += n
        return b

    is_open = False

    def isOpen(self):
        return False

    def write(self, b):
        raise AssertionError('the receive path must never write')


def _speed_pkt(vx=100, vy=0, vz=0, volt=118):
    p = bytearray([0xFF, 0xFB, 10, 0x0A]) + vx.to_bytes(2, 'little', signed=True) + \
        vy.to_bytes(2, 'little', signed=True) + vz.to_bytes(2, 'little', signed=True) + bytes([volt])
    p.append(sum(p[2:]) & 0xFF)
    return bytes(p)


def _encoder_pkt(m=(1, -2, 3, -4)):
    p = bytearray([0xFF, 0xFB, 19, 0x0D]) + b''.join(v.to_bytes(4, 'little', signed=True) for v in m)
    p.append(sum(p[2:]) & 0xFF)
    return bytes(p)


def _load_lib(tmp_path, patched):
    src = (ROOT / 'scripts' / 'Rosmaster_Lib.py').read_text(encoding='utf-8')
    if patched:
        src = insert_rosmaster_rc.patch(src)
    name = 'rlib_%s' % ('p' if patched else 'u')
    (tmp_path / (name + '.py')).write_text(src, encoding='utf-8')
    sys.path.insert(0, str(tmp_path))
    try:
        import importlib
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(tmp_path))


def _run_stream(lib, data):
    bot = lib.Rosmaster(car_type=5, com='unused', serial_link=_FakeSerial(data))
    with pytest.raises(EOFError):
        bot._Rosmaster__receive_data_loop()
    return bot


@pytest.mark.parametrize('patched', [False, True])
def test_existing_packets_unchanged_with_rc_reports_interleaved(tmp_path, patched):
    lib = _load_lib(tmp_path, patched)
    stream = b''
    for k in range(25):
        stream += _speed_pkt() + _encoder_pkt((k, -k, 2 * k, -2 * k)) + rc.build_packet(frame(), k, 20)
    bot = _run_stream(lib, stream)
    d = bot.get_serial_diagnostics()
    assert d['checksum_errors'] == 0 and d['encoder_packets'] == 25 and d['valid_packets'] == 75
    assert bot.get_motor_encoder() == [24, -24, 48, -48] or tuple(bot.get_motor_encoder()) == (24, -24, 48, -48)
    if patched:
        payload, stamp, count = bot.get_rc_sbus_report()
        assert count == 25 and rc.parse_payload(payload).seq == 24
    else:
        assert not hasattr(bot, 'get_rc_sbus_report')


def test_patched_lib_without_new_firmware_reports_none(tmp_path):
    bot = _run_stream(_load_lib(tmp_path, True), _speed_pkt() + _encoder_pkt())
    assert bot.get_rc_sbus_report() is None


def test_insert_rosmaster_is_additive_and_refuses_twice():
    src = (ROOT / 'scripts' / 'Rosmaster_Lib.py').read_text(encoding='utf-8')
    out = insert_rosmaster_rc.patch(src)
    removed = [l for l in __import__('difflib').ndiff(src.splitlines(), out.splitlines()) if l.startswith('- ')]
    assert removed == []
    with pytest.raises(SystemExit):
        insert_rosmaster_rc.patch(out)


def test_usb_discovery_still_recognises_board_with_rc_reports():
    stream = b''.join(_speed_pkt() + rc.build_packet(frame(), k, 10) + _encoder_pkt() for k in range(6))
    assert atlas_usb_identity.protocol_matches(stream, 'yahboom')
    assert not atlas_usb_identity.protocol_matches(stream, 'gps')
    assert not atlas_usb_identity.protocol_matches(stream, 'imu')


# ------------------------------------------------------------------ forwarding into the Test Lab
def _feed(fwd, reports, t0=100.0, dt=0.04):
    out = []
    for i, p in enumerate(reports):
        fwd.handle(p[4:-1], t0 + i * dt, 1.7e9 + i * dt, out.append)
    return out


def test_forwarder_publishes_only_new_fresh_frames_rate_limited():
    fwd = rc.RcReportForwarder(FrameForwarder('sbus'))
    reports = [rc.build_packet(frame(), seq=i * 3 % 256, age_ms=12) for i in range(100)]   # 25 Hz, 4 s
    out = _feed(fwd, reports)
    assert 40 <= len(out) <= 80          # never above the 20 Hz bridge contract over 4 s
    for m in out:
        assert m['proto'] == 'sbus' and core.decode_sbus(bytes.fromhex(m['hex'])) is not None


def test_repeated_or_stale_reports_never_publish():
    fwd = rc.RcReportForwarder(FrameForwarder('sbus'))
    same = [rc.build_packet(frame(), seq=5, age_ms=12)] * 20
    assert len(_feed(fwd, same)) == 1
    stale = [rc.build_packet(frame(), seq=s, age_ms=400) for s in range(6, 30)]
    assert _feed(fwd, stale, t0=200) == []
    never = [rc.build_packet(None, 0, None)] * 10
    assert _feed(fwd, never, t0=300) == []
    s = fwd.status()
    assert s['stale_or_repeat'] >= 19 + 24 and s['never_received'] == 10


def test_test_lab_reaches_live_failsafe_and_lost_from_yahboom_path():
    lab = core.FlyskyLab()
    fwd = rc.RcReportForwarder(FrameForwarder('sbus'))
    ch = [200 + 150 * i for i in range(10)] + [992] * 6
    t = 0.0
    for i in range(10):
        t = i * 0.04
        fwd.handle(rc.build_packet(frame(ch), i, 10)[4:-1], t, t, lambda m: lab.ingest_message(m, t, t))
    assert core.link_state(True, lab.last, t)[0] == 'LIVE'
    assert list(lab.last.raw[:10]) == ch[:10]
    for j in range(10, 20):
        t = j * 0.04
        fwd.handle(rc.build_packet(frame(ch, failsafe=True), j, 10)[4:-1], t, t,
                   lambda m: lab.ingest_message(m, t, t))
    assert core.link_state(True, lab.last, t)[0] == 'FAILSAFE'
    # receiver unplugged: firmware keeps reporting but the frame ages -> nothing new published
    for j in range(20, 120):
        t = j * 0.04
        fwd.handle(rc.build_packet(frame(ch), 19, 40 * (j - 19))[4:-1], t, t, lambda m: lab.ingest_message(m, t, t))
    assert core.link_state(True, lab.last, t)[0] == 'LOST'
