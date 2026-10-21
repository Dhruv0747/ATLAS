"""Stage32 UI fix: user-facing session states are derived from real frame counts/freshness (Node, offline)."""
import json, shutil, subprocess, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('node'), 'node not installed')
class SessionStates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = json.loads(subprocess.check_output(['node', str(ROOT / 'tests/vision3d_state_cases.js')], text=True))

    def t(self, k): return self.r[k]['title']

    def test_starting_and_waiting_are_not_live(self):
        self.assertEqual(self.t('checking'), 'Starting'); self.assertEqual(self.r['checking']['chips']['ir']['label'], 'Starting')
        self.assertEqual(self.t('wait'), 'Waiting for frames'); self.assertNotEqual(self.r['wait']['tone'], 'ok')
        self.assertIn('no frames yet', self.r['wait']['driver'])

    def test_driver_running_without_frames_is_no_frames_received(self):
        v = self.r['nofr']; self.assertEqual(v['title'], 'No frames received'); self.assertEqual(v['chips']['ir']['label'], 'No frames received')
        self.assertIn('not a working view', v['text']); self.assertEqual(v['tone'], 'warn')

    def test_session_end_remembers_that_no_frames_arrived(self):
        v = self.r['ended_none']; self.assertEqual(v['title'], 'No frames received'); self.assertIn('Infrared delivered no frames', v['text'])

    def test_live_only_with_fresh_frames_and_end_summary(self):
        self.assertEqual(self.t('live'), 'Live'); self.assertEqual(self.r['live']['chips']['ir']['label'], 'Live')
        self.assertEqual(self.t('stale'), 'Frames stopped'); self.assertEqual(self.r['stale']['chips']['ir']['label'], 'No new frames')
        v = self.r['ended_ok']; self.assertEqual(v['title'], 'Stopped safely'); self.assertIn('Infrared: 1,624 frames received', v['text'])
        self.assertIn('stopped checking in for more than 4 seconds', self.r['lease']['text'])

    def test_combined_mode_names_the_missing_stream(self):
        v = self.r['mixed']; self.assertEqual(v['title'], 'No frames received'); self.assertEqual(v['missing'], ['ir']); self.assertEqual(v['live'], ['depth'])
        self.assertEqual(v['chips']['depth']['label'], 'Live'); self.assertIn('Depth is live', v['text'])

    def test_resource_block_is_not_called_unsupported(self):
        v = self.r['blocked']; self.assertEqual(v['title'], 'Resource blocked'); self.assertIn('76.2%', v['text'])
        self.assertIn('says nothing about whether the camera mode works', v['text']); self.assertNotIn('unsupported', v['text'].lower())

    def test_new_worker_resets_session_evidence_and_plain_states(self):
        self.assertEqual(self.t('newworker'), 'Waiting for frames')
        self.assertEqual(self.t('none'), 'Viewer not installed'); self.assertEqual(self.t('off'), 'Camera off')

    def test_mode_notes(self):
        m = self.r['modes']
        self.assertEqual((m['verified']['note'], m['verified']['disabled']), ('Tested', False))
        self.assertEqual((m['untested']['note'], m['untested']['disabled']), ('Not yet tested', False))
        self.assertEqual((m['unsupported']['note'], m['unsupported']['disabled']), ('Not supported (tested)', True))
        self.assertEqual((m['cloud_blocked']['note'], m['cloud_blocked']['disabled']), ('Calibration required', True))
        self.assertFalse(m['cloud_ok']['disabled']); self.assertEqual(m['depth_default']['note'], 'Tested')


class StaticWiring(unittest.TestCase):
    def test_page_loads_state_module_first_and_uses_it(self):
        html = (ROOT / 'web/v2/vision3d.html').read_text(); js = (ROOT / 'web/v2/vision3d.js').read_text()
        self.assertLess(html.index('/v2/vision3d_state.js'), html.index('/v2/vision3d.js'))
        self.assertIn('VS.sessionView(rt, status && status.streams, memo', js); self.assertIn('VS.modeNote(m, info)', js)
        for stale in ("'Camera streaming'", "'Session finished'", "'Checking before start'"):
            self.assertNotIn(stale, js)

    def test_ui_uses_only_fields_the_deployed_receiver_provides(self):
        js = (ROOT / 'web/v2/vision3d.js').read_text() + (ROOT / 'web/v2/vision3d_state.js').read_text()
        for candidate_only in ('ir_delivery', 'last_session', 'ir_boundaries', 'ir_api'):
            self.assertNotIn(candidate_only, js)


if __name__ == '__main__':
    unittest.main()
