"""Offline real-method tests; importing this never imports ROS or starts a node."""
import ast
from collections import deque
import random
from pathlib import Path
import subprocess
import threading
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).resolve().parents[1]/'scripts'/'atlas_status_web.py'
BASE = 'cd75929'


def load(source, clock, fallback):
    cls = next(n for n in ast.parse(source).body
               if isinstance(n, ast.ClassDef) and n.name == 'AtlasRosNode')
    methods = [n for n in cls.body if isinstance(n, ast.FunctionDef)
               and n.name in ('snapshot', '_set')]
    ns = dict(time=clock, deque=deque, sensor_hub_cache_snapshot=lambda: fallback)
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(SOURCE), 'exec'), ns)
    return ns


def baseline():
    return subprocess.check_output(['git','show',f'{BASE}:project_atlas/scripts/atlas_status_web.py'],
                                   cwd=SOURCE.parent, encoding='utf-8')


def state(histories=None):
    histories = histories or {'lidar': [99, 99.5, 100]}
    return SimpleNamespace(lock=threading.Lock(), ready=True,
        data={k:dict(value=i,ts=199) for i,k in enumerate(histories)},
        update_times={k:deque(v,maxlen=128) for k,v in histories.items()})


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.mono=100; self.wall=200
        self.clock=SimpleNamespace(monotonic=lambda:self.mono,time=lambda:self.wall)
        self.fallback={'data':{},'updated_at':0}
        self.old=load(baseline(),self.clock,self.fallback)
        self.new=load(SOURCE.read_text(encoding='utf-8'),self.clock,self.fallback)

    def compare(self,a,b):
        self.assertEqual(self.old['snapshot'](a),self.new['snapshot'](b))

    def test_randomized_history_expiration_and_updates(self):
        rng=random.Random(32)
        h={str(i):sorted(rng.uniform(80,100) for _ in range(rng.randrange(129))) for i in range(100)}
        a,b=state(h),state(h)
        for _ in range(40):
            self.compare(a,b)
            self.mono+=rng.random();self.wall+=.5
            k=str(rng.randrange(100))
            self.old['_set'](a,k,5);self.new['_set'](b,k,5)

    def test_boundary_duplicates_and_empty(self):
        h={'boundary':[90,90,90.000001,99,100],'empty':[],'duplicate':[100,100], 'single':[99]}
        self.compare(state(h),state(h))

    def test_fallback_freshness_and_notes(self):
        a,b=state({'bat_current':[99,100],'bat_percent':[99,100]}),state({'bat_current':[99,100],'bat_percent':[99,100]})
        self.fallback['data']={'bat_current':dict(value=123,ts=199.5)}
        self.compare(a,b)
        self.wall=201; self.compare(a,b)

    def test_no_cached_age_or_safety_value(self):
        a,b=state(),state()
        for value in (True,False,True):
            self.old['_set'](a,'stop_latched',value);self.new['_set'](b,'stop_latched',value)
            self.wall+=3; self.mono+=3;self.compare(a,b)

    def test_bounded_callback_history(self):
        a,b=state(),state()
        for i in range(200):
            self.mono+=.01
            self.old['_set'](a,'new',i);self.new['_set'](b,'new',i)
        self.assertEqual(list(a.update_times['new']),list(b.update_times['new']))
        self.assertEqual(len(b.update_times['new']),128)
        self.compare(a,b)


if __name__=='__main__': unittest.main()
