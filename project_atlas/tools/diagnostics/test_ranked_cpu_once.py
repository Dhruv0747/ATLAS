import unittest
import tempfile
from unittest.mock import patch
from pathlib import Path
import ranked_cpu_once as R


def row(ticks, birth=1, **changes):
    return dict(ticks=ticks, birth=birth, process_birth=2, tgid=10,
                cgroup=next(iter(R.GROUPS)), executable='/usr/bin/python3.10',
                profile_eligible=True, **changes)


class Tests(unittest.TestCase):
    def test_unrelated_process_keeps_total_without_exe_resolution(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'10';root.mkdir()
            fields=['0']*20;fields[11]='10';fields[12]='5';fields[19]='2'
            (root/'stat').write_text('10 (test) '+' '.join(fields))
            (root/'cgroup').write_text('0::/unrelated')
            (root/'comm').write_text('test')
            with patch.object(Path,'resolve',side_effect=AssertionError('must not resolve unrelated exe')):
                result=R.snapshot(lambda pid: {},Path(directory))
            self.assertEqual(result['process:10']['ticks'],15)
            self.assertFalse(result['process:10']['profile_eligible'])

    def test_rank_current_deltas(self):
        a={str(i):row(10000) for i in range(10,18)}
        b={str(i):row(10000+i) for i in range(10,18)}
        self.assertEqual(list(R.choose(a,b)), ['17','16','15','14','13','12'])

    def test_process_totals_not_double_counted(self):
        a={'10':row(1), 'process:10':dict(row(1),profile_eligible=False)}
        b={'10':row(2), 'process:10':dict(row(999),profile_eligible=False)}
        self.assertEqual(R.choose(a,b),{'10':1})

    def test_identity_changes_rejected(self):
        for key,value in [('birth',9),('process_birth',9),('tgid',9),('cgroup','other'),('executable','other')]:
            with self.assertRaises(RuntimeError):
                R.choose({'10':row(1)},{'10':dict(row(10),**{key:value})})

    def test_no_load_rejected(self):
        with self.assertRaises(RuntimeError):R.choose({'10':row(10)},{'10':row(9)})

    def test_allowlist(self):
        group=next(iter(R.GROUPS))
        self.assertTrue(R.allowed('/usr/bin/python3.10',group,1000,1000))
        self.assertFalse(R.allowed('/usr/bin/python3.10','other',1000,1000))
        self.assertFalse(R.allowed('/usr/bin/python3.10',group,0,1000))
        self.assertFalse(R.allowed('/tmp/unknown',group,1000,1000))

    def test_command_bounds(self):
        args=R.command('/perf',10,'/out',[10,20])
        self.assertIn('cpu-clock:u',args)
        self.assertIn('--no-inherit',args)
        self.assertIn('49',args)
        self.assertEqual(args[-1],'20')
        for tids in [[],[1],[10,10],list(range(10,17))]:
            with self.assertRaises(ValueError):R.command('/perf',10,'/out',tids)

    def test_loaded_guard_preservation(self):
        helper=R.load_helper(Path(__file__).with_name('native_dashboard_cpu_once.py'))
        self.assertIsNone(helper.checked_cpu(99,True))
        self.assertEqual(helper.checked_cpu(99,False),99)
        with self.assertRaises(RuntimeError):helper.checked_cpu(float('nan'),True)
        with self.assertRaises(RuntimeError):helper.require_off({'state':'RUNNING'},1)
        self.assertEqual(helper.TARGET_UNIT,'rover-status-web')
        self.assertEqual(len(helper.EXTRA_UNITS),10)


if __name__=='__main__':unittest.main()
