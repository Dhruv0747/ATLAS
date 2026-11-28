import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
from concurrent.futures import Future
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from atlas_initialization_observer import InitializationObserver

class ObserverTests(unittest.TestCase):
    def make(self, emit):
        node=Mock(); node.get_clock.return_value.now.return_value.nanoseconds=42
        return InitializationObserver(node, emit=emit, encode=lambda m:b'cdr')
    def test_disabled_no_publisher_or_extra_call(self):
        with patch.dict(os.environ, {'ATLAS_CHECKPOINT_EVENTS':'0'}):
            node=Mock(); o=InitializationObserver(node); c=Mock(); r=object()
            self.assertIs(o.call(c,r,'/service'),c.call_async.return_value)
            c.call_async.assert_called_once_with(r);node.create_publisher.assert_not_called()
    def test_same_future_and_exactly_one_request(self):
        e=[];o=self.make(e.append);f=Future();c=Mock();c.call_async.return_value=f;r=object()
        self.assertIs(o.call(c,r,'/service'),f);f.set_result(object())
        c.call_async.assert_called_once_with(r)
        self.assertEqual([v['phase'] for v in e],['request_attempt','response_received'])
        self.assertEqual(e[0]['call_id'],e[1]['call_id'])
    def test_diagnostic_failure_does_not_change_future(self):
        o=self.make(Mock(side_effect=OSError()));f=Future();c=Mock();c.call_async.return_value=f
        self.assertIs(o.call(c,object(),'/service'),f);f.set_result(object());self.assertEqual(o.failures,2)
    def test_original_call_exception_preserved(self):
        o=self.make(lambda e:None);c=Mock();c.call_async.side_effect=RuntimeError('original')
        with self.assertRaisesRegex(RuntimeError,'original'):o.call(c,object(),'/service')
    def test_response_failure_remains_on_future(self):
        e=[];o=self.make(e.append);f=Future();c=Mock();c.call_async.return_value=f
        o.call(c,object(),'/service');exc=ValueError();f.set_exception(exc)
        self.assertIs(f.exception(),exc);self.assertEqual(e[-1]['phase'],'response_exception')

if __name__=='__main__':unittest.main()
