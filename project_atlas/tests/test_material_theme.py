"""Static UI contract checks. Never connects to ATLAS or initializes ROS."""
from pathlib import Path
import re
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[2]
WEB=ROOT/'project_atlas/web/v2'
LINK='<link rel="stylesheet" href="/v2/material.css">'


class MaterialThemeTests(unittest.TestCase):
    def test_all_ten_pages_load_theme_last(self):
        pages=list(WEB.glob('*.html'))
        self.assertEqual(len(pages),10)
        for page in pages:
            content=page.read_text(encoding='utf-8')
            with self.subTest(page=page.name):
                self.assertEqual(content.count(LINK),1)
                self.assertIn(LINK+'</head>',content)
                self.assertEqual(re.findall(r'<link[^>]+rel="stylesheet"[^>]*>',content)[-1],LINK)

    def test_page_controls_scripts_ids_unchanged_from_reviewed_baseline(self):
        for page in WEB.glob('*.html'):
            before=subprocess.check_output(['git','show','36c5a08:'+page.relative_to(ROOT).as_posix()],cwd=ROOT).decode()
            self.assertEqual(page.read_text(encoding='utf-8').replace(LINK,'').rstrip('\n'),before.replace('\r\n','\n').rstrip('\n'),page.name)

    def test_theme_is_small_and_has_no_external_requests_or_active_effects(self):
        css=(WEB/'material.css').read_text()
        self.assertLess(len(css.encode()),6000)
        self.assertNotRegex(css,r'url\(|@import|@keyframes|will-change|requestAnimationFrame')
        self.assertEqual(set(re.findall(r'blur\(([^)]+)\)',css)),{'6px'})
        self.assertIn('html:not(.lite) body >',css)
        self.assertIn('backdrop-filter:none!important',css)

    def test_no_layout_visibility_or_pointer_overrides(self):
        css=re.sub(r'/\*.*?\*/','',(WEB/'material.css').read_text(),flags=re.S)
        self.assertNotRegex(css,r'(?:^|[;{])\s*(?:display|visibility|pointer-events|position|z-index|transform|width|height|overflow)\s*:')

    def test_safety_colours_and_accessibility_preserved(self):
        css=(WEB/'material.css').read_text()
        for token in ('--terrain:#7CC242','--amber:#F2B33D','--signal:#FF4D5E',
                      '#v2Estop',':disabled',':focus-visible','prefers-reduced-motion',
                      'prefers-reduced-transparency','forced-colors:active','html.lite'):
            self.assertIn(token,css)


if __name__=='__main__':unittest.main()
