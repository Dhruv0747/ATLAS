import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import atlas_flysky_core as C  # noqa: E402


def sbus(ch=None, **kw):
    return C.encode_sbus(ch or [992] * 16, **kw)


def lab_with(frames, t0=100.0, dt=0.014):
    lab = C.FlyskyLab()
    for k, f in enumerate(frames):
        lab.ingest_message({'proto': 'sbus' if len(f) == 25 else 'ibus', 'hex': f.hex()}, t0 + k * dt, 1.7e9 + k * dt)
    return lab


class SbusFrames(unittest.TestCase):
    def test_roundtrip_all_channels_and_flags(self):
        ch = [172, 992, 1811, 0, 2047, 5, 1000, 300, 1700, 1, 2, 3, 4, 5, 6, 7]
        f = C.decode_sbus(sbus(ch, ch17=True, ch18=False, frame_lost=True, failsafe=False))
        self.assertEqual(list(f.raw), ch)
        self.assertEqual((f.ch17, f.ch18, f.frame_lost, f.failsafe), (True, False, True, False))
        f = C.decode_sbus(sbus(ch, failsafe=True))
        self.assertTrue(f.failsafe)

    def test_known_vector(self):
        # all channels at centre 992 -> known 11-bit packing
        f = sbus([992] * 16)
        self.assertEqual(f[0], 0x0F)
        self.assertEqual(f[1], 992 & 0xFF)
        self.assertEqual(f[2] & 0x07, (992 >> 8) & 0x07)
        self.assertEqual(len(f), 25)

    def test_reject_bad_header_end_and_length(self):
        good = bytearray(sbus())
        for bad in (b'\x00' + bytes(good[1:]), bytes(good[:24]) + b'\x01', bytes(good[:24]), bytes(good) + b'\x00'):
            self.assertIsNone(C.decode_sbus(bad))
        for end in C.SBUS_ENDS:
            self.assertIsNotNone(C.decode_sbus(sbus(end=end)))


class IbusFrames(unittest.TestCase):
    def test_roundtrip_and_checksum(self):
        f = C.decode_ibus(C.encode_ibus([1000, 1500, 2000, 1234]))
        self.assertEqual(f.raw[:4], (1000, 1500, 2000, 1234))
        self.assertIsNone(f.failsafe)          # iBUS has no flags: not observable, not "clear"
        bad = bytearray(C.encode_ibus([1500] * 14)); bad[5] ^= 1
        self.assertIsNone(C.decode_ibus(bytes(bad)))
        self.assertIsNone(C.decode_ibus(C.encode_ibus([1500] * 14)[:31]))


class StreamParsing(unittest.TestCase):
    def test_split_across_chunks(self):
        p = C.StreamParser('sbus'); f = sbus([172] + [992] * 15); out = []
        for i in range(0, 25, 7):
            out += p.feed(f[i:i + 7], 1.0 + i * 0.0001, 0.0)
        self.assertEqual(len(out), 1); self.assertEqual(p.valid, 1)

    def test_garbage_then_frames_resync(self):
        p = C.StreamParser('sbus'); noise = bytes([1, 2, 3, 0x55, 0xAA])
        out = p.feed(noise + sbus() + noise + sbus(), 1.0, 0.0)
        self.assertEqual(len(out), 2); self.assertGreater(p.garbage, 0); self.assertGreaterEqual(p.resyncs, 1)

    def test_false_header_inside_data_does_not_lose_following_frame(self):
        p = C.StreamParser('sbus')
        junk = bytes([0x0F] + [0x11] * 10)            # looks like a header, never completes validly
        out = p.feed(junk + sbus(), 1.0, 0.0)
        self.assertEqual(len(out), 1)
        self.assertGreaterEqual(p.invalid, 1)

    def test_incomplete_frame_expires(self):
        p = C.StreamParser('sbus')
        self.assertEqual(p.feed(sbus()[:12], 1.0, 0.0), [])
        self.assertEqual(p.feed(sbus(), 1.0 + C.PARTIAL_TIMEOUT_S + 0.01, 0.0).__len__(), 1)
        self.assertEqual(p.incomplete, 1)

    def test_random_bytes_never_crash_and_buffer_is_bounded(self):
        rng = random.Random(7)
        for proto in ('sbus', 'ibus'):
            p = C.StreamParser(proto)
            for k in range(2000):
                p.feed(bytes(rng.randrange(256) for _ in range(rng.randrange(1, 90))), k * 0.001, 0.0)
                self.assertLessEqual(len(p.buf), C.BUF_MAX)

    def test_ibus_stream(self):
        p = C.StreamParser('ibus')
        out = p.feed(C.encode_ibus([1500] * 14) * 3, 1.0, 0.0)
        self.assertEqual(len(out), 3)

    def test_wrong_protocol_name(self):
        with self.assertRaises(ValueError):
            C.StreamParser('ppm')


class Normalising(unittest.TestCase):
    def test_nominal_scale(self):
        self.assertAlmostEqual(C.normalize('sbus', 172), -1.0, 3)
        self.assertAlmostEqual(C.normalize('sbus', 992), 0.0, 3)
        self.assertAlmostEqual(C.normalize('sbus', 1811), 1.0, 3)
        self.assertAlmostEqual(C.normalize('ibus', 1000), -1.0)
        self.assertAlmostEqual(C.normalize('ibus', 2000), 1.0)

    def test_glitch_is_clamped(self):
        self.assertEqual(C.normalize('sbus', 2047), 1.25)
        self.assertEqual(C.normalize('ibus', 0), -1.25)


class LinkStates(unittest.TestCase):
    def test_no_source_is_not_verified_with_reason(self):
        st, why = C.link_state(False, None, 0.0)
        self.assertEqual(st, 'NO_SOURCE'); self.assertEqual(C.LINK_LABEL[st], 'SIGNAL NOT VERIFIED')
        self.assertIn('does not forward SBUS', why)

    def test_source_without_frames_is_not_verified_and_never_connected(self):
        st, why = C.link_state(True, None, 5.0, invalid=7)
        self.assertEqual(C.LINK_LABEL[st], 'SIGNAL NOT VERIFIED'); self.assertIn('7 invalid', why)

    def test_paired_receiver_alone_never_says_connected(self):
        # a source exists, bytes arrive, but none validates
        lab = C.FlyskyLab()
        lab.ingest_message({'proto': 'sbus', 'hex': (b'\x0f' + b'\x55' * 24).hex()}, 1.0, 0.0)
        s = lab.snapshot(1.1, True)
        self.assertNotEqual(s['link']['label'], 'CONNECTED'); self.assertFalse(s['link']['verified'])

    def test_live_stale_lost_progression(self):
        lab = lab_with([sbus()] * 10); last = lab.last.rx
        self.assertEqual(lab.snapshot(last + 0.1, True)['link']['state'], 'LIVE')
        self.assertEqual(lab.snapshot(last + 1.0, True)['link']['state'], 'STALE')
        self.assertEqual(lab.snapshot(last + 5.0, True)['link']['state'], 'LOST')
        self.assertFalse(lab.snapshot(last + 1.0, True)['link']['verified'])

    def test_failsafe_and_frame_lost_flags(self):
        lab = lab_with([sbus(failsafe=True)] * 3); s = lab.snapshot(lab.last.rx + 0.1, True)
        self.assertEqual(s['link']['state'], 'FAILSAFE'); self.assertTrue(s['flags']['failsafe']); self.assertEqual(s['flags']['failsafe_count'], 3)
        lab = lab_with([sbus(frame_lost=True)] * 3); s = lab.snapshot(lab.last.rx + 0.1, True)
        self.assertEqual(s['link']['state'], 'FRAME_LOST'); self.assertEqual(s['flags']['frame_lost_count'], 3)

    def test_ibus_flags_are_not_observable_not_clear(self):
        lab = lab_with([C.encode_ibus([1500] * 14)] * 3); s = lab.snapshot(lab.last.rx + 0.1, True)
        self.assertFalse(s['flags']['observable']); self.assertIsNone(s['flags']['failsafe']); self.assertIsNone(s['flags']['frame_lost'])
        self.assertIn('Not observable', s['flags']['note']); self.assertEqual(s['link']['state'], 'LIVE')

    def test_rssi_is_never_invented(self):
        s = lab_with([sbus()] * 3).snapshot(100.1, True)
        self.assertFalse(s['rssi']['available']); self.assertNotIn('value', s['rssi'])

    def test_rate(self):
        lab = lab_with([sbus()] * 100, dt=0.02); self.assertAlmostEqual(lab.rate_hz(lab.last.rx), 50.0, delta=2)


class ChannelMapping(unittest.TestCase):
    def test_discovers_moving_channel_without_assuming_roles(self):
        frames = []
        for k in range(60):
            ch = [992] * 16; ch[6] = 992 + k * 12          # only CH7 moves
            frames.append(sbus(ch))
        s = lab_with(frames).snapshot(100.9, True)
        moved = [c['channel'] for c in s['channels'] if c['moved']]
        self.assertEqual(moved, [7])
        c7 = s['channels'][6]; self.assertEqual(c7['kind'], 'analog'); self.assertEqual(c7['direction'], 'up')
        self.assertEqual([c['kind'] for c in s['channels'] if c['channel'] != 7], ['not moved yet'] * 15)

    def test_switch_classification_two_and_three_position(self):
        frames = []
        for k in range(90):
            ch = [992] * 16
            ch[4] = 172 if (k // 15) % 2 else 1811                 # 2-pos
            ch[5] = (172, 992, 1811)[(k // 10) % 3]                # 3-pos
            frames.append(sbus(ch))
        s = lab_with(frames).snapshot(101.4, True)
        self.assertEqual(s['channels'][4]['kind'], 'switch'); self.assertEqual(s['channels'][5]['kind'], 'switch')
        self.assertIn(s['channels'][4]['switch_position'], ('low', 'high'))
        self.assertEqual(s['channels'][5]['levels'], 3)

    def test_direction_up_down_steady(self):
        lab = C.FlyskyLab(); t = 100.0
        for k in range(30):
            ch = [992] * 16; ch[0] = 992 - k * 20; lab.ingest_message({'proto': 'sbus', 'hex': sbus(ch).hex()}, t + k * 0.01, 0.0)
        self.assertEqual(lab.snapshot(t + 0.3, True)['channels'][0]['direction'], 'down')
        for k in range(60):
            lab.ingest_message({'proto': 'sbus', 'hex': sbus([992 - 580] + [992] * 15).hex()}, t + 1.0 + k * 0.01, 0.0)
        self.assertEqual(lab.snapshot(t + 1.6, True)['channels'][0]['direction'], 'steady')

    def test_reset_ranges(self):
        lab = lab_with([sbus([172] + [992] * 15), sbus([1811] + [992] * 15)])
        self.assertEqual(lab.snapshot(100.1, True)['channels'][0]['range'], 1639)
        lab.tracker.reset_ranges(); lab.ingest_message({'proto': 'sbus', 'hex': sbus().hex()}, 101.0, 0.0)
        self.assertEqual(lab.snapshot(101.1, True)['channels'][0]['range'], 0)

    def test_bad_source_messages_are_counted_not_fatal(self):
        lab = C.FlyskyLab()
        for m in (None, {}, {'proto': 'ppm', 'hex': '00'}, {'proto': 'sbus', 'hex': 'zz'}, {'proto': 'sbus', 'hex': ''}, 'x', {'proto': 'sbus', 'hex': 'ab' * 500}):
            self.assertEqual(lab.ingest_message(m, 1.0, 0.0), 0)
        self.assertEqual(lab.bad_messages, 7)


class Recording(unittest.TestCase):
    def test_csv_has_raw_and_normalised_flags_and_state(self):
        lab = C.FlyskyLab(); s = C.LabSession('abcdef012345', 1.7e9, 100.0); lab.session = s
        s.event('session_start', 1.7e9, 100.0)
        for k in range(20):
            ch = [992] * 16; ch[0] = 172 + k * 80
            lab.ingest_message({'proto': 'sbus', 'hex': sbus(ch, failsafe=(k == 19)).hex()}, 100.0 + k * 0.05, 1.7e9 + k * 0.05)
        text = s.to_csv().splitlines(); head = text[0].split(',')
        self.assertEqual(head[:6], ['iso_time_utc', 'monotonic_s', 'session_id', 'event', 'protocol', 'link_state'])
        self.assertIn('ch1_raw', head); self.assertIn('ch16_norm', head)
        row = dict(zip(head, text[5].split(',')))
        self.assertEqual(row['event'], 'sample'); self.assertTrue(row['ch1_raw'].isdigit()); self.assertEqual(row['failsafe'], '0')
        self.assertEqual(dict(zip(head, text[-1].split(',')))['failsafe'], '1')
        self.assertEqual({len(r.split(',')) for r in text}, {len(head)})

    def test_ibus_rows_leave_flags_blank(self):
        lab = C.FlyskyLab(); s = C.LabSession('abcdef012345', 1.7e9, 100.0); lab.session = s
        lab.ingest_message({'proto': 'ibus', 'hex': C.encode_ibus([1500] * 14).hex()}, 100.0, 1.7e9)
        head = s.to_csv().splitlines()[0].split(','); row = dict(zip(head, s.to_csv().splitlines()[1].split(',')))
        self.assertEqual((row['failsafe'], row['frame_lost']), ('', ''))
        self.assertEqual(row['ch15_raw'], '')

    def test_recording_rate_is_decimated_and_bounded(self):
        lab = C.FlyskyLab(); s = C.LabSession('abcdef012345', 1.7e9, 100.0); lab.session = s
        for k in range(1000):
            lab.ingest_message({'proto': 'sbus', 'hex': sbus().hex()}, 100.0 + k * 0.004, 1.7e9)   # 250 Hz in
        self.assertLessEqual(s.frames, 4.0 * C.SESSION_HZ + 3)
        s2 = C.LabSession('x' * 12, 0.0, 0.0); s2.rows = [()] * C.MAX_SESSION_ROWS
        s2.add_frame(C.decode_sbus(sbus(), 1.0, 1.0), 'LIVE', 0.0); self.assertTrue(s2.truncated)

    def test_graph_is_bounded_and_decimated(self):
        lab = lab_with([sbus()] * 3000, dt=0.004)
        s = lab.snapshot(lab.last.rx, True)
        self.assertLessEqual(len(s['graph']['t']), int(C.GRAPH_S * C.GRAPH_HZ) + 8)


class NoActuationSurface(unittest.TestCase):
    def test_core_has_no_io_or_message_imports(self):
        src = (Path(C.__file__)).read_text()
        for bad in ('import rclpy', 'import serial', 'import socket', 'geometry_msgs', 'cmd_vel', 'create_publisher', 'subprocess'):
            self.assertNotIn(bad, src)


if __name__ == '__main__':
    unittest.main()
