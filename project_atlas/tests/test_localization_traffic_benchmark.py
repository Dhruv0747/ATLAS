import importlib.util
import inspect
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

TOOLS=Path(__file__).resolve().parents[1]/'tools/diagnostics'
sys.path.insert(0,str(TOOLS))
spec=importlib.util.spec_from_file_location('traffic',TOOLS/'benchmark_localization_traffic.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)


class TrafficTests(unittest.TestCase):
    def test_window_preserves_order_timing_and_payload(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'test.db3'
            with sqlite3.connect(path) as c:
                c.execute('create table topics(id integer,name text,type text)')
                c.execute('create table messages(id integer,topic_id integer,timestamp integer,data blob)')
                for i,topic in enumerate(M.TOPICS):
                    c.execute('insert into topics values(?,?,?)',(i,topic,'test/msg/Type'))
                    c.execute('insert into messages values(?,?,?,?)',(i,i,1_000_000_000+i*100_000_000,bytes([i])))
            before=path.read_bytes()
            events,static=M.window(path,0,2)
            self.assertEqual([e[0] for e in events],[0,.1,.2,.3,.4])
            self.assertEqual([e[3] for e in events],[bytes([i]) for i in range(5)])
            self.assertEqual(static,[])
            self.assertEqual(path.read_bytes(),before)
            with self.assertRaises(ValueError):M.window(path,2,2)

    def test_bounds(self):
        for offset,duration in ((-1,2),(241,2),(0,1),(0,16)):
            with self.assertRaises(ValueError):M.window(Path('absent'),offset,duration)

    def test_unknown_callbacks_rejected_before_import(self):
        with self.assertRaises(ValueError):M.callbacks(b'bad',b'bad')

    def test_timed_loop_keeps_production_blocking_wait(self):
        source=inspect.getsource(M.run)
        self.assertIn('ex.spin_once(timeout_sec=None)',source)
        self.assertNotIn('timeout_sec=.005',source)
        self.assertIn('msg!=sequence[topic][i]',source)
        self.assertIn('buffer.can_transform',source)


if __name__=='__main__':unittest.main()
