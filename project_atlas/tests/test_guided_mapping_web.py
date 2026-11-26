"""Guided mapping phase 1b: status web pass-through + dashboard overlay (static checks; no ROS, no Node). 2026-11-26."""
import ast
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'scripts' / 'atlas_status_web.py'
tree = ast.parse(SRC.read_text(encoding='utf-8'))
ns = {'json': json}
body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'visible_mapping_quality'
        or (isinstance(n, ast.Assign) and any(getattr(t, 'id', '') == 'MAPPING_QUALITY_MAX_AGE_S' for t in n.targets))]
exec(compile(ast.Module(body=body, type_ignores=[]), str(SRC), 'exec'), ns)
visible_mapping_quality = ns['visible_mapping_quality']
JS = (ROOT / 'web' / 'v2' / 'mapping-quality.js').read_text(encoding='utf-8')
PAGE = (ROOT / 'web' / 'v2' / 'mapping.html').read_text(encoding='utf-8')


class StatusWebTests(unittest.TestCase):
    def item(self, payload, age=1.0):
        return {'value': payload if isinstance(payload, str) else json.dumps(payload), 'age': age}

    def test_fresh_valid_payload_passes(self):
        out = visible_mapping_quality(self.item({'schema': 1, 'state': 'active', 'rows': []}))
        self.assertEqual(out['state'], 'active')

    def test_stale_bad_or_missing_is_none(self):
        self.assertIsNone(visible_mapping_quality(None))
        self.assertIsNone(visible_mapping_quality(self.item({'schema': 1, 'state': 'active'}, age=30.0)))
        self.assertIsNone(visible_mapping_quality(self.item('{broken')))
        self.assertIsNone(visible_mapping_quality(self.item({'schema': 2, 'state': 'active'})))
        self.assertIsNone(visible_mapping_quality(self.item([1, 2])))

    def test_snapshot_and_subscription_wired(self):
        text = SRC.read_text(encoding='utf-8')
        self.assertIn('"/atlas/mapping_quality"', text)
        self.assertIn('result["mapping_quality"] = visible_mapping_quality(', text)


class OverlayTests(unittest.TestCase):
    def test_page_loads_overlay(self):
        self.assertRegex(PAGE, r'<script src="/v2/mapping-quality\.js\?v=\d{8}[a-z]*" defer></script>')

    def test_overlay_is_read_only(self):
        self.assertNotIn('fetch(', JS)             # reads the /api/map state the page already polls
        self.assertNotIn('XMLHttpRequest', JS)
        self.assertNotRegex(JS, r'cmd_vel|/api/places|/api/autonomy')

    def test_overlay_text_is_english(self):
        self.assertFalse(any('ऀ' <= ch <= 'ॿ' for ch in JS))
        for word in ('kya', 'kaise', 'karo', 'rasta', 'hai'):
            self.assertNotRegex(JS, r'\b' + word + r'\b')

    def test_overlay_uses_page_transform_and_escapes(self):
        self.assertIn('worldPixel(', JS)
        self.assertIn('baseDraw.apply(this, arguments)', JS)
        self.assertRegex(JS, r'function esc\(')
        for field in ('rows', 'tile_m', 'prompts', 'verdict_text', 'objects', 'frontiers', 'notes'):
            self.assertIn(field, JS)

    def test_overlay_only_when_mapping(self):
        self.assertRegex(JS, r"q\.state\s*!==\s*'active'|q\.state\s*===\s*'inactive'")

    def test_saved_map_check_view(self):
        """2026-11-26 owner: "where can I see that the map needs updating" -> orange map-change boxes + card."""
        self.assertIn('SAVED MAP CHECK', JS)
        self.assertIn('map_changes', JS)
        self.assertRegex(JS, r"q\.state\s*===\s*'map_check'")
        self.assertIn('Orange = the LiDAR keeps seeing something the saved map does not have', JS)


class PositionsUiTests(unittest.TestCase):
    def test_card_shows_positions_and_scans(self):
        self.assertIn('c.positions', JS)
        self.assertIn('scans used', JS)


if __name__ == '__main__':
    unittest.main()
