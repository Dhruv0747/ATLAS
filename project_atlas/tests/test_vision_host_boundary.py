"""Offline boundary tests; no ROS, camera, model or live Dashboard requests."""
import base64
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from atlas_vision_cache_only import cached_rgb, decode_frame, HTTPFrames
from atlas_vision_lab_host import Host, Handler, peer_allowed
from atlas_vision_feature_lab import Lab


class Cache(unittest.TestCase):
    def setUp(self):
        from PIL import Image
        b = io.BytesIO(); Image.new('RGB', (2, 2)).save(b, format='PNG')
        self.png = b.getvalue()
        self.msg = NS(header=NS(stamp=NS(sec=100, nanosec=100000000)))
        self.svc = NS(lock=threading.RLock(), transport=NS(error=''), error='',
                      clock=lambda: 10., wall=lambda: 100.2,
                      received={'rgb': 9.9}, messages={'rgb': self.msg},
                      cache={'rgb': self.png, 'rgb_message': self.msg,
                             'rgb_received': 9.9, 'rgb_key': ('rgb', 100.1)})
        self.runtime = dict(state='ACTIVE', driver_pid=42,
                            startup_guard_baseline_monotonic_s=5.)

    def test_cache_returns_original_stamp_and_no_side_effects(self):
        self.svc.touch = lambda: self.fail('lease touched')
        self.svc.frame = lambda _: self.fail('conversion/transport path used')
        result = cached_rgb(self.svc, self.runtime)
        self.assertEqual(result['stamp_ns'], '100100000000')
        image, stamp = decode_frame(result, 100200000000, 10.)
        self.assertEqual(image.shape, (2, 2, 3)); self.assertEqual(stamp, 100100000000)

    def test_missing_disconnected_stale_future_rejected(self):
        for field, value in [('transport', None), ('error', 'disconnected')]:
            with self.subTest(field=field):
                old = getattr(self.svc, field); setattr(self.svc, field, value)
                with self.assertRaises(ValueError): cached_rgb(self.svc, self.runtime)
                setattr(self.svc, field, old)
        for state in ('OFF', 'CHECKING'):
            with self.assertRaises(ValueError): cached_rgb(self.svc, dict(self.runtime, state=state))
        for wall in (101., 99.):
            self.svc.wall = lambda: wall
            with self.assertRaises(ValueError): cached_rgb(self.svc, self.runtime)

    def test_expired_camera_and_reception_rejected(self):
        for start in (-60., float('nan'), 11.):
            with self.assertRaises(ValueError): cached_rgb(self.svc, dict(self.runtime, startup_guard_baseline_monotonic_s=start))
        self.svc.cache['rgb_received'] = 9.
        with self.assertRaises(ValueError): cached_rgb(self.svc, self.runtime)

    def test_client_rejects_delayed_payload_and_invalid_png(self):
        result = cached_rgb(self.svc, self.runtime)
        for now in (101000000000, 99000000000):
            with self.assertRaises(ValueError): decode_frame(result, now, 10.)
        with self.assertRaises(ValueError): decode_frame(dict(result, png=base64.b64encode(b'not PNG').decode()), 100200000000, 10.)
        with self.assertRaises(ValueError): decode_frame(dict(result, received_mono=8.), 100200000000, 10.)

    def test_interleaved_reader_refreshes_by_original_age(self):
        provider=HTTPFrames(); provider.deadline=40.; provider.fetched=10.
        provider.data=cached_rgb(self.svc,self.runtime)
        fresh=dict(provider.data,stamp_ns='100500000000',received_mono=10.3)
        with patch('atlas_vision_cache_only.time.monotonic',return_value=10.3), patch('atlas_vision_cache_only.time.time_ns',return_value=100550000000), patch.object(provider,'_fetch',return_value=fresh) as fetch:
            _, stamp=provider.read()
            self.assertEqual(stamp,100500000000);fetch.assert_called_once()

    def test_slow_drip_has_total_deadline_and_closes_socket(self):
        class Drip:
            closed=False
            def settimeout(self,t): self.timeout=t
            def connect(self,*a): pass
            def sendall(self,*a): pass
            def recv(self,*a):
                time.sleep(min(.05,self.timeout));return b'H'
            def close(self): self.closed=True
        drip=Drip();provider=HTTPFrames();start=time.monotonic()
        with patch('atlas_vision_cache_only.socket.socket',return_value=drip):
            with self.assertRaises(ValueError):provider._fetch()
        self.assertLess(time.monotonic()-start,.8);self.assertTrue(drip.closed)

    def test_cancel_interrupts_owned_socket(self):
        provider=HTTPFrames()
        from unittest.mock import Mock
        sock=Mock();provider.socket=sock;provider.close()
        sock.shutdown.assert_called_once();sock.close.assert_called_once()
        with self.assertRaises(ValueError):provider.read()


@unittest.skipUnless(hasattr(socket, 'SO_PEERCRED'), 'Linux Unix-socket peer credentials')
class HTTP(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.path = Path(self.tmp.name)/'host.sock'
        self.lab = NS(status=lambda: {'features': [], 'active': None}, stop=lambda: None)
        self.host = Host(self.path, self.lab, lambda: None)
        self.thread = threading.Thread(target=self.host.serve_forever, daemon=True); self.thread.start()

    def tearDown(self):
        self.host.shutdown(); self.host.server_close(); self.thread.join(); self.tmp.cleanup()

    def request(self, raw):
        with socket.socket(socket.AF_UNIX) as s:
            s.settimeout(2); s.connect(str(self.path)); s.sendall(raw)
            out=b''
            while True:
                chunk=s.recv(65536)
                if not chunk:break
                out+=chunk
            return out

    def test_peer_credentials_and_private_socket(self):
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertFalse(peer_allowed(os.getuid()+1, os.getuid()))
        self.assertTrue(peer_allowed(os.getuid(), os.getuid()))

    def test_status_authenticated_transport_and_bad_host(self):
        self.assertIn(b'200 OK', self.request(b'GET /api/vision3d/features HTTP/1.0\r\nHost: localhost:8099\r\n\r\n'))
        self.assertIn(b'403', self.request(b'GET /api/vision3d/features HTTP/1.0\r\nHost: evil.example\r\n\r\n'))

    def test_no_camera_or_motor_routes_and_csrf(self):
        for route in ('/api/vision3d/viewer', '/api/drive', '/api/vision3d/frame?kind=rgb'):
            self.assertIn(b'404', self.request(('GET '+route+' HTTP/1.0\r\nHost: localhost:8099\r\n\r\n').encode()))
        self.assertIn(b'403', self.request(b'POST /api/vision3d/features HTTP/1.0\r\nHost: localhost:8099\r\nContent-Length: 17\r\n\r\n{"action":"stop"}'))

    def test_oversized_and_rate_limited(self):
        self.assertIn(b'413', self.request(b'POST /api/vision3d/features HTTP/1.0\r\nHost: localhost:8099\r\nOrigin: http://localhost:8099\r\nX-Atlas-Vision3D: 1\r\nContent-Type: application/json\r\nContent-Length: 9999\r\n\r\n'))
        self.host.requests.extend([time.monotonic()]*8)
        self.assertIn(b'429', self.request(b'GET /api/vision3d/features HTTP/1.0\r\nHost: localhost:8099\r\n\r\n'))


class ProviderLifecycle(unittest.TestCase):
    def exercise_injected_worker(self, mode):
        # Reuse the existing synthetic-worker harness, but exercise ONLY the new
        # injected provider branch. Never load the engine, camera runtime or ROS.
        import test_vision_feature_lifecycle as harness
        providers=[]
        class Frames:
            def __init__(self):
                self.deadline=time.monotonic()+30; self.closed=False;providers.append(self)
            def read(self):
                import numpy as np
                return np.zeros((2,2,3),dtype=np.uint8),time.time_ns()
            def close(self):self.closed=True
        original=Lab
        def make(*args,**kwargs):
            lab=original(*args,**kwargs,frame_factory=Frames)
            run=lab.run
            if mode=='guard_failure':
                lab.run=lambda feature,c,viewer,r:run(feature,dict(c,duration_s=3),viewer,r)
            return lab
        with patch.object(harness,'Lab',side_effect=make):harness.Lifecycle().exercise(mode)
        self.assertTrue(providers);self.assertTrue(all(p.closed for p in providers))

    def test_injected_worker_completes_and_closes(self):self.exercise_injected_worker('complete')
    def test_injected_worker_safety_abort_closes(self):self.exercise_injected_worker('guard_failure')

    def test_missing_cache_closes_provider_without_importing_camera_runtime(self):
        with tempfile.TemporaryDirectory() as d:
            provider = NS(deadline=time.monotonic()+30, closed=False)
            def read(): raise ValueError('cache unavailable')
            provider.read=read
            provider.close=lambda: setattr(provider, 'closed', True)
            lab=Lab(d,frame_factory=lambda: provider)
            lab.settings=lambda: dict(duration_s=2,model_sha256='test')
            guard=NS(observe=lambda *a: {},ticks=lambda: 0,cpu_delta=lambda *a: 60)
            with patch.dict(sys.modules, {'atlas_vision_feature_guard':guard,'atlas_vision3d_runtime':None}), patch('subprocess.Popen') as spawn:
                lab.start('object',None); lab.thread.join(4)
                self.assertFalse(lab.thread.is_alive()); spawn.assert_not_called()
            self.assertTrue(provider.closed); self.assertIsNone(lab.active)
            self.assertIn('cache unavailable',lab.reports['object']['reason'])

    def test_cache_route_does_not_touch_even_when_missing(self):
        import atlas_vision3d_web as web
        svc=NS(touch=lambda: self.fail('viewer lease touched'))
        handler=NS(path='/api/vision3d/cached-rgb',client_address=('127.0.0.1',1),
                   wfile=io.BytesIO(),send_response=lambda c: None,
                   send_header=lambda *a: None,end_headers=lambda: None)
        runtime=NS(SESSION=NS(status=lambda: {'state':'OFF'}))
        with patch.dict(sys.modules, {'atlas_vision3d_runtime':runtime}), patch('atlas_vision_cache_only.cached_rgb',side_effect=ValueError('missing')):
            self.assertTrue(web.serve(handler,svc))
        self.assertIn(b'missing',handler.wfile.getvalue())


if __name__ == '__main__': unittest.main()
