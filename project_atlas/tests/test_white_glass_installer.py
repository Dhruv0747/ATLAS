"""Offline installer primitives only; never calls deployment main()."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('theme_deploy',ROOT/'tools/diagnostics/deploy_white_glass_once.py')
D=importlib.util.module_from_spec(spec);spec.loader.exec_module(D)


class InstallerTests(unittest.TestCase):
    def test_all_pages_preserve_original_bytes(self):
        for name in D.NAMES:
            raw=(ROOT/'web/v2'/name).read_bytes().replace(D.LINK,b'')
            self.assertEqual(D.patched(raw).replace(D.LINK,b''),raw,name)

    def test_ambiguous_or_already_installed_rejected(self):
        for raw in (b'no head',b'</head></head>',D.LINK+b'</head>'):
            with self.assertRaises(RuntimeError):D.patched(raw)

    def test_atomic_write_and_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'page.html';D.atomic(p,b'original');D.atomic(p,b'candidate')
            self.assertEqual(p.read_bytes(),b'candidate')
            D.atomic(p,b'original');self.assertEqual(p.read_bytes(),b'original')
            self.assertEqual(list(Path(tmp).iterdir()),[p])

    def test_candidate_hash_pin(self):
        self.assertEqual(D.sha((ROOT/'web/v2/material.css').read_bytes()),D.CSS_SHA)
