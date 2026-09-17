import unittest
import ast
import time
import json
from pathlib import Path
from types import SimpleNamespace
from atlas_serial_lines import SerialLines, CameraReplyGuard

class SerialTests(unittest.TestCase):
    def test_real_tick_drains_burst_without_blocking_readline(self):
        tree=ast.parse(Path(__file__).with_name('ultrasonic_arduino_bridge.py').read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='UltrasonicArduinoBridge')
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='tick')
        env={'time':time,'json':json,'String':lambda **kw:SimpleNamespace(**kw),
             'SERIAL_STALE_REOPEN_SECONDS':10}
        exec(compile(ast.Module(body=[method],type_ignores=[]),'<tick>','exec'),env)
        class Port:
            def __init__(self): self.data=b''.join(('ACK,%d\n'%i).encode() for i in range(200))
            @property
            def in_waiting(self): return len(self.data)
            def read(self,n):
                result,self.data=self.data[:n],self.data[n:]
                return result
        received=[]
        obj=SimpleNamespace(ser=Port(),rx_lines=SerialLines(),rx_high_water=0,
            rx_processed=0,rx_diag_time=time.monotonic(),last_serial_rx=time.time(),
            flush_dashboard_cache=lambda:None,read_local_camera_commands=lambda:None,
            handle_line=received.append)
        for _ in range(10):
            if len(received)==200: break
            env['tick'](obj)
        self.assertEqual(received,['ACK,%d'%i for i in range(200)])
        self.assertEqual(obj.rx_processed,200)
    def test_fragmented_lines(self):
        q=SerialLines()
        q.feed(b'AMG,part')
        self.assertIsNone(q.pop())
        q.feed(b'2\r\nBME,ok\n')
        self.assertEqual(q.pop(),'AMG,part2')
        self.assertEqual(q.pop(),'BME,ok')
        self.assertIsNone(q.pop())
    def test_burst_preserves_order(self):
        q=SerialLines()
        q.feed(b''.join(('ACK,%d\n'%i).encode() for i in range(500)))
        self.assertEqual([q.pop() for _ in range(500)],['ACK,%d'%i for i in range(500)])
    def test_bounded_overflow(self):
        q=SerialLines(capacity=10)
        with self.assertRaises(BufferError): q.feed(b'x'*11)
        self.assertEqual(len(q.data),0)
    def test_idle_does_not_adopt_old_target(self):
        g=CameraReplyGuard()
        self.assertTrue(g.accept(1500))
        g.sent(1250)
        self.assertFalse(g.accept(1770))
        self.assertFalse(g.accept(1300))
        self.assertTrue(g.accept(1250))
    def test_latest_target_wins(self):
        g=CameraReplyGuard()
        g.sent(1300)
        g.sent(1250)
        self.assertFalse(g.accept(1300))
        self.assertTrue(g.accept(1250))

if __name__=='__main__': unittest.main()
