"""No boot-time ordering cycles among repo user units (no systemd needed).

2026-10-10 22:24: atlas-localization-monitor (WantedBy=default.target) was
After=atlas-localization.service, which is After=default.target. systemd broke
the cycle by deleting the monitor's start job, so it silently did not run.
"""
from pathlib import Path
import re
import unittest

UNITS = Path(__file__).parents[1] / 'systemd/user'


def parse(path):
    after, wanted = set(), set()
    files = [path] + sorted(path.with_name(path.name + '.d').glob('*.conf'))
    for f in files:
        for line in f.read_text(encoding='utf-8').splitlines():
            m = re.match(r'\s*(After|WantedBy)\s*=\s*(.*)', line)
            if m:
                (after if m.group(1) == 'After' else wanted).update(m.group(2).split())
    return after, wanted


class OrderingTests(unittest.TestCase):
    def test_boot_units_not_after_units_that_wait_for_default_target(self):
        units = {p.name: parse(p) for p in UNITS.glob('*.service')}
        waits = {n for n, (after, _) in units.items() if 'default.target' in after}
        bad = [(n, sorted(after & waits)) for n, (after, wanted) in units.items()
               if 'default.target' in wanted and after & waits]
        self.assertEqual(bad, [])

    def test_monitor_unit_has_no_cycle(self):
        after, wanted = parse(UNITS / 'atlas-localization-monitor.service')
        self.assertIn('default.target', wanted)
        self.assertNotIn('atlas-localization.service', after)


if __name__ == '__main__':
    unittest.main()
