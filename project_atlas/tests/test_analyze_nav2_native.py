import unittest
from project_atlas.tools.diagnostics.analyze_nav2_native import stacks, thread_cpu


class NativeAnalysisTests(unittest.TestCase):
    def test_counts_once_and_retains_overlap(self):
        r=stacks('node 12 50 cpu-clock:u:\n\tWaitSetImpl::attach_condition\n\tWaitSetImpl::detach_condition\n\tExecutor::wait_for_work')
        self.assertEqual(r['samples'],1)
        self.assertEqual(r['inclusive_paths'],{'wait_set_attach_detach':1,'executor_wait_for_work':1})
        self.assertEqual(r['sampled_user_cpu_ns_by_tid'],{'12':50})

    def test_two_threads_and_bond(self):
        r=stacks('a 12 50 cpu-clock:u:\n\tbond::Bond::publishStatus\n\nb 13 50 cpu-clock:u:\n\trcl_take+1')
        self.assertEqual(r['samples_by_tid'],{'12':1,'13':1})
        self.assertEqual(r['inclusive_paths'],{'bond_publish':1,'subscription_dispatch':1})

    def test_reject_bad_or_truncated_sample(self):
        for s in ('invalid', 'a 12 50 cpu-clock:u:', 'a 12 0 cpu-clock:u:\n frame'):
            with self.assertRaises(ValueError): stacks(s)

    def rows(self):
        return [dict(monotonic=t,threads={'12':dict(tgid=12,birth=1,ticks=n)}) for t,n in [(0,0),(2,40)]]

    def test_cpu_units(self):
        self.assertEqual(thread_cpu(self.rows(),100)['one_core_percent_by_tgid'],{12:20})

    def test_pid_reuse(self):
        rows=self.rows();rows[1]['threads']['12']['birth']=2
        self.assertEqual(thread_cpu(rows,100)['one_core_percent_by_tgid'],{})

    def test_counter_time_and_hz(self):
        for kind in ('time','counter','hz'):
            rows=self.rows()
            if kind=='time':rows[1]['monotonic']=0
            if kind=='counter':rows[1]['threads']['12']['ticks']=-1
            with self.assertRaises(ValueError):thread_cpu(rows,0 if kind=='hz' else 100)


if __name__ == '__main__': unittest.main()
