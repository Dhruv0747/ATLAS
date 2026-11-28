import copy
import unittest
from cpu_accounting_report import analyze


def fixture():
    p = dict(name='worker', birth=10, user=0, system=0, cgroup='test', kernel=False)
    q = dict(p, user=100)
    return dict(hz=100, cpus=2, observer_cpu_s=.02, samples=[
        dict(monotonic=1, cpu=[0]*8, processes={'1':p}),
        dict(monotonic=2, cpu=[100,0,20,60,10,5,5,0], processes={'1':q})])


class AccountingTests(unittest.TestCase):
    def test_machine_and_core_units(self):
        r = analyze(fixture())
        self.assertEqual(r['cpu_percent'], 65)
        self.assertEqual(r['processes'][0]['one_core_percent'], 100)
        self.assertEqual(r['accounted_pid_percent'], 50)
        self.assertEqual(r['observer_capacity_percent'], 1)

    def test_pid_reuse_is_not_charged(self):
        j=fixture(); j['samples'][1]['processes']['1']['birth']=11
        self.assertEqual(analyze(j)['accounted_pid_percent'], 0)
        self.assertEqual(analyze(j)['new_or_reused_pid_intervals'], 1)

    def test_kernel_is_subset_not_extra(self):
        j=fixture(); j['samples'][1]['processes']['1']['kernel']=True
        r=analyze(j)
        self.assertEqual(r['kernel_thread_percent'],r['accounted_pid_percent'])
        self.assertEqual(r['cpu_percent'],65)

    def test_all_processes_not_only_top10(self):
        j=fixture()
        for s in j['samples']:
            s['processes']={str(i):copy.deepcopy(s['processes']['1']) for i in range(12)}
        r=analyze(j)
        self.assertEqual(len(r['processes']),12)
        self.assertGreater(r['accounted_pid_percent'],r['top10_percent'])

    def test_bad_clock_rejected(self):
        j=fixture(); j['samples'][1]['monotonic']=1
        with self.assertRaises(ValueError): analyze(j)

    def test_counter_reset_rejected(self):
        j=fixture(); j['samples'][1]['cpu'][0]=-1
        with self.assertRaises(ValueError): analyze(j)

    def test_nonuniform_windows_are_tick_weighted(self):
        j=fixture()
        j['samples'].append(dict(monotonic=4,cpu=[100,0,20,460,10,5,5,0],processes={}))
        self.assertAlmostEqual(analyze(j)['cpu_percent'],130/600*100)


if __name__ == '__main__': unittest.main()
