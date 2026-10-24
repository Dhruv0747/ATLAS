import unittest
from analyze_ranked_cpu import summarize


def sample(t, process_ticks, thread_ticks, birth=1):
    return dict(monotonic=t,cpu=70,phase='baseline',threads={
        'process:10':dict(ticks=process_ticks,birth=birth,tgid=10,cgroup='g',kind='process_total',name='p'),
        '10':dict(ticks=thread_ticks,birth=birth,process_birth=birth,tgid=10,cgroup='g',kind='thread',name='t')})


class Tests(unittest.TestCase):
    def test_no_double_count(self):
        r=summarize([sample(1,0,0),sample(2,20,10)])
        self.assertEqual(r['groups_one_core_pct'],[('g',20)])
        self.assertEqual(r['thread'][0]['cpu_one_core_pct'],10)
    def test_reused_identity(self):
        r=summarize([sample(1,0,0),sample(2,20,10,2)])
        self.assertEqual(r['process_total'],[])
    def test_regression(self):
        with self.assertRaises(ValueError):summarize([sample(1,20,10),sample(2,0,0)])
    def test_time(self):
        with self.assertRaises(ValueError):summarize([sample(1,0,0),sample(1,20,10)])
    def test_cgroup_change(self):
        a,b=sample(1,0,0),sample(2,20,10)
        for row in b['threads'].values():row['cgroup']='other'
        self.assertEqual(summarize([a,b])['process_total'],[])
    def test_migration_preserves_earlier_group(self):
        rows=[sample(1,0,0),sample(2,20,10),sample(3,30,20),sample(4,60,30)]
        for r in rows[2:]:
            for q in r['threads'].values():q['cgroup']='other'
        groups=dict(summarize(rows)['groups_one_core_pct'])
        self.assertAlmostEqual(groups['g'],20/3)
        self.assertAlmostEqual(groups['other'],10)


if __name__=='__main__':unittest.main()
