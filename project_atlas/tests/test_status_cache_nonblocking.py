"""Only the /api/status cache boundary; AST loading avoids all ROS imports."""
import ast
from pathlib import Path
import threading
import time
from types import SimpleNamespace as NS
import unittest

SOURCE=Path(__file__).resolve().parents[1]/'scripts/atlas_status_web.py'


def load():
    nodes=[]
    for n in ast.parse(SOURCE.read_text(encoding='utf-8')).body:
        if isinstance(n,ast.FunctionDef) and n.name in ('snapshot','_refresh_status_cache'):nodes.append(n)
    state={'now':100.,'ros':0}
    def ros():
        state['ros']+=1
        return {'control_policy':{'age':state['now']-99.,'value':state['ros']}}
    ns=dict(time=NS(monotonic=lambda:state['now'],strftime=lambda _: 'offline'),threading=threading,
            _slow_cache_lock=threading.Lock(),
            _slow_cache={'ts':0.,'attempted':0.,'pending':False,'network':{},'system':{},'services':{}},
            network_status=lambda:{'route':'test'},system_status=lambda:{'ram_percent':50},
            services=lambda:{'test':'active'},ROS=NS(snapshot=ros),TODO=[])
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(SOURCE),'exec'),ns)
    return ns,state


class CacheTests(unittest.TestCase):
    def test_slow_refresh_never_blocks_requests_and_is_single_flight(self):
        ns,state=load();entered=threading.Event();release=threading.Event();calls=[]
        def slow():
            calls.append(1);entered.set();release.wait(2);return {'route':'test'}
        ns['network_status']=slow
        try:
            started=time.monotonic();out=ns['snapshot']()
            self.assertLess(time.monotonic()-started,.2)
            self.assertTrue(entered.wait(.2));self.assertIsNone(out['system'].get('ram_percent'))
            for _ in range(4):ns['snapshot']()
            self.assertEqual(len(calls),1)
            self.assertEqual(state['ros'],5)
        finally:release.set()

    def test_stale_values_not_presented_as_current(self):
        ns,state=load();ns['_slow_cache'].update(ts=97.,pending=True,network={'route':'old'},system={'ram_percent':50},services={'test':'active'})
        out=ns['snapshot']()
        self.assertNotEqual(out['network'].get('route'),'old')
        self.assertIsNone(out['system'].get('ram_percent'))
        self.assertEqual(out['services'],{})

    def test_fresh_cache_does_not_cache_safety(self):
        ns,state=load();ns['_slow_cache'].update(ts=99.,system={'ram_percent':50})
        a=ns['snapshot']();state['now']=100.2;b=ns['snapshot']()
        self.assertEqual(b['system']['ram_percent'],50)
        self.assertNotEqual(a['ros'],b['ros'])

    def test_slow_completion_uses_collection_start_not_end_for_age(self):
        ns,state=load()
        ns['network_status']=lambda:(state.update(now=103.) or {'route':'late'})
        ns['_slow_cache']['pending']=True
        ns['_refresh_status_cache'](100.)
        ns['_slow_cache']['pending']=True
        out=ns['snapshot']()
        self.assertIsNone(out['system'].get('ram_percent'))

    def test_collector_failure_does_not_publish_partial_or_zero(self):
        ns,state=load()
        def fail():raise OSError('offline failure')
        ns['system_status']=fail;ns['_slow_cache']['pending']=True
        ns['_refresh_status_cache'](100.)
        self.assertFalse(ns['_slow_cache']['pending'])
        out=ns['snapshot']()
        self.assertIsNone(out['system'].get('ram_percent'))


if __name__=='__main__':unittest.main()
