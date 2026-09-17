"""No microphone, serial access or real speaker output."""
import unittest
from types import SimpleNamespace
from atlas_intercom import packed_mono_pcm, packet, HEADER, PLAY_STREAM


class IntercomAudioTests(unittest.TestCase):
    def frame(self, samples=320, data=b'\x00\x01'*320+b'\x7f'*128, fmt='s16', layout='mono'):
        return SimpleNamespace(samples=samples, planes=[data],
            format=SimpleNamespace(name=fmt), layout=SimpleNamespace(name=layout))

    def test_padding_never_reaches_speaker(self):
        data = packed_mono_pcm(self.frame())
        self.assertEqual(len(data), 640)
        self.assertEqual(data, b'\x00\x01'*320)

    def test_initial_resampler_frame(self):
        self.assertEqual(len(packed_mono_pcm(self.frame(samples=304))), 608)

    def test_reject_truncated_plane(self):
        with self.assertRaises(ValueError): packed_mono_pcm(self.frame(data=b'\0'*2))

    def test_reject_wrong_format(self):
        with self.assertRaises(ValueError): packed_mono_pcm(self.frame(fmt='fltp'))
        with self.assertRaises(ValueError): packed_mono_pcm(self.frame(layout='stereo'))

    def test_packet_declares_only_sample_bytes(self):
        data = packet(PLAY_STREAM, packed_mono_pcm(self.frame()))
        self.assertEqual(HEADER.unpack_from(data)[3], 640)
        self.assertEqual(len(data), HEADER.size+640)

    def test_actual_pyav_resampler(self):
        try:
            from av import AudioFrame
            from av.audio.resampler import AudioResampler
        except ImportError:
            self.skipTest('PyAV test runs in Jetson intercom venv')
        resampler = AudioResampler(format='s16', layout='mono', rate=16000)
        for _ in range(5):
            frame = AudioFrame(format='s16', layout='stereo', samples=960)
            frame.sample_rate = 48000
            frame.planes[0].update(b'\0'*3840)
            for out in resampler.resample(frame):
                self.assertEqual(len(packed_mono_pcm(out)), out.samples*2)


if __name__ == '__main__': unittest.main()
