"""Synthetic protocol/unit tests, NOT physical camera accuracy qualification."""
import io
import json
import math
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import atlas_vision3d_core as C
import atlas_vision3d_web as W
import atlas_web_v2 as V


def image(values=(1000,0,2000,65535),big=False,encoding='16UC1',padding=0):
    fmt='f' if encoding=='32FC1' else 'H';bpp=4 if fmt=='f' else 2
    rows=[struct.pack(('>' if big else '<')+fmt*2,*values[i:i+2])+b'\0'*padding for i in (0,2)]
    return N(width=2,height=2,encoding=encoding,step=2*bpp+padding,is_bigendian=big,data=b''.join(rows),
             header=N(frame_id='astra_depth_optical_frame',stamp=N(sec=100,nanosec=0)))


def info():return N(width=2,height=2,k=[2.,0,0,0,2.,0,0,0,1],d=[],header=N(frame_id='astra_depth_optical_frame'))


def cloud(big=False):
    return N(width=2,height=1,point_step=16,row_step=36,is_bigendian=big,
             data=struct.pack(('>' if big else '<')+'8f',1,2,3,99,float('nan'),0,0,0)+b'PAD!',
             fields=[N(name=k,offset=i*4,datatype=7,count=1) for i,k in enumerate('xyz')],header=image().header)


class CoreTests(unittest.TestCase):
    def test_mm_m_and_invalid(self):
        m=image();self.assertEqual(C.depth_at(m,0,0),1);self.assertIsNone(C.depth_at(m,1,0));self.assertIsNone(C.depth_at(m,1,1))
    def test_float_invalid(self):
        m=image((1.2,float('nan'),float('inf'),-1),encoding='32FC1');self.assertAlmostEqual(C.depth_at(m,0,0),1.2,5)
        for u,v in ((1,0),(0,1),(1,1)):self.assertIsNone(C.depth_at(m,u,v))
    def test_big_endian_padded(self):self.assertEqual(C.depth_at(image(big=True,padding=4),0,1),2)
    def test_bounds(self):
        with self.assertRaises(ValueError):C.depth_at(image(),2,0)
    def test_truncated(self):
        m=image();m.data=m.data[:-1]
        with self.assertRaises(ValueError):C.preview(m,'depth')
    def test_xyz_range(self):
        v=C.measure(image(),info(),0,1);self.assertEqual(v['xyz_m'],[0.,1.,2.]);self.assertAlmostEqual(v['range_m'],math.sqrt(5))
    def test_no_info_does_not_invent_xyz(self):self.assertIsNone(C.measure(image(),None,0,0)['xyz_m'])
    def test_distortion_rejected(self):
        i=info();i.d=[.1];self.assertIsNone(C.measure(image(),i,0,0)['xyz_m'])
    def test_frame_mismatch_rejected(self):
        i=info();i.header.frame_id='base_link';self.assertIsNone(C.measure(image(),i,0,0)['xyz_m'])
    def test_bad_focal(self):
        i=info();i.k[0]=0;self.assertIsNone(C.measure(image(),i,0,0)['xyz_m'])
    def test_png_and_counts(self):
        png,d=C.preview(image(),'depth');self.assertTrue(png.startswith(b'\x89PNG'));self.assertEqual((d['sampled_valid'],d['sampled_invalid']),(2,2))
    def test_unknown_encoding(self):
        m=image();m.encoding='madeup'
        with self.assertRaises(ValueError):C.preview(m,'depth')
    def test_rgb_bgr(self):
        m=image();m.encoding='bgr8';m.step=6;m.data=b'\xff\0\0'*4;self.assertTrue(C.preview(m,'rgb')[0])
    def test_cloud_endian_padding_nan(self):
        for b in (False,True):self.assertEqual(C.cloud_points(cloud(b))['points'],[[1.,2.,3.]])
    def test_cloud_invalid_field(self):
        m=cloud();m.fields[0].datatype=8
        with self.assertRaises(ValueError):C.cloud_points(m)
    def test_cloud_non_optical_frame(self):
        m=cloud();m.header.frame_id='base_link'
        with self.assertRaises(ValueError):C.cloud_points(m)
    def test_nan_distortion(self):
        i=info();i.d=[float('nan')];self.assertIsNone(C.measure(image(),i,0,0)['xyz_m'])
    def test_cloud_cap(self):
        m=cloud();m.width=10000;m.row_step=160000;m.data=struct.pack('<4f',0,0,1,0)*10000
        self.assertLessEqual(len(C.cloud_points(m)['points']),6000)
    def test_shadow_no_control(self):
        o=C.obstacle_prototype([[0,0,.5],[0,0,3]]);self.assertTrue(o['shadow_only']);self.assertEqual(o['candidate_count'],1)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.now=100.;self.s=W.VisionService({},clock=lambda:self.now,wall=lambda:self.now)
    def test_default_unconfigured_no_threads(self):
        self.s.touch();self.assertIsNone(self.s.transport);self.assertFalse(self.s.status()['recording'])
    def test_fresh_stale(self):
        self.s.ingest('depth',image());self.assertEqual(self.s.status()['streams']['depth']['state'],'ACTIVE');self.now+=3
        with self.assertRaises(ValueError):self.s.pixel(0,0)
    def test_clock_mismatch(self):
        self.s.ingest('depth',image());self.s.wall=lambda:50
        self.assertEqual(self.s.status()['streams']['depth']['state'],'STALE')
    def test_backward_stamp_rejected(self):
        self.s.ingest('depth',image());m=image();m.header.stamp.sec=99;self.s.ingest('depth',m)
        self.assertEqual(self.s.stats['depth']['stamp_regressions'],1)
    def test_rate_throttle(self):
        self.s.ingest('depth',image());m=image();m.header.stamp.nanosec=100;self.s.ingest('depth',m)
        self.assertEqual(self.s.stats['depth']['viewer_throttled'],1)
    def test_bad_frame_removes_data(self):
        self.s.ingest('depth',image());m=image();m.data=b'';self.s.ingest('depth',m)
        self.assertEqual(self.s.status()['streams']['depth']['state'],'SENSOR ERROR')
    def test_pixel_and_cloud(self):
        self.s.ingest('depth',image());self.s.ingest('depth_info',info_with_stamp())
        self.s.ingest('cloud',cloud());self.assertEqual(self.s.pixel(0,0)['depth_z_m'],1)
        # Stage32: any metric cloud now requires a VALIDATED calibration file (none exists in the repository)
        with self.assertRaisesRegex(ValueError,'CALIBRATION BLOCKED'):self.s.cloud()
        doc={'frame_id':'astra_depth_optical_frame','width':2,'height':2,'k':[2.,0,0,0,2.,0,0,0,1],'d':[0,0,0,0,0]}
        with patch.object(W.geometry,'calibration_state',return_value={'state':'VALIDATED','reason':'fixture','calibration':doc}):
            self.assertTrue(self.s.cloud()['points'])
    def test_stop_clears(self):
        self.s.ingest('depth',image());self.s.stop();self.assertEqual(self.s.messages,{})
    def test_manifest_rejects_pi_camera(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'m.json';p.write_text(json.dumps({'topics':{'rgb':'/camera/image_raw'}}))
            with patch.dict(os.environ,{'ATLAS_VISION3D_MANIFEST':str(p)}):
                with self.assertRaises(ValueError):W.read_manifest()
    def test_http_routes_read_only(self):
        class H:
            path='/api/vision3d/status';wfile=io.BytesIO()
            def send_response(s,c):s.code=c
            def send_header(*a):pass
            def end_headers(*a):pass
        h=H();self.assertTrue(W.serve(h,self.s));self.assertEqual(h.code,200);self.assertTrue(json.loads(h.wfile.getvalue())['read_only'])
        h.path='/api/vision3d/record';W.serve(h,self.s);self.assertEqual(h.code,404)
    def test_preview_cached(self):
        self.s.ingest('depth',image())
        with patch.object(C,'preview',wraps=C.preview) as p:
            self.s.frame('depth');self.s.frame('depth');self.assertEqual(p.call_count,1)
    def test_exact_route_and_home(self):
        self.assertTrue(V.resolve('/v2/vision3d'));src=(Path(__file__).parents[1]/'web/v2/index.html').read_text(encoding='utf-8')
        import re;self.assertEqual(len(re.findall(r'<a [^>]*href="/v2/vision3d"',src)),1)
    def test_no_control_interfaces(self):
        src=Path(W.__file__).read_text()
        for forbidden in ('create_publisher(', 'create_client(', 'subprocess.', 'serial.Serial(', 'VideoCapture('):self.assertNotIn(forbidden,src)
    def test_idle_cleanup(self):
        class T:
            stopped=False
            def stop(s):s.stopped=True
        t=T();self.s.transport=t;self.s.touched=0;self.s._idle();self.assertTrue(t.stopped)
    def test_failed_transport_backoff(self):
        calls=[]
        class T:
            def start(s,*a):calls.append(1);raise RuntimeError('offline ROS')
            def stop(s):pass
        self.s.manifest={'topics':{'depth':'/astra/depth'}};self.s.factory=T
        self.s.touch();self.s.touch();self.assertEqual(len(calls),1)
    def test_stop_then_reconnect_fresh_frame(self):
        self.s.ingest('depth',image());self.s.frame('depth');self.s.stop()
        self.s.ingest('depth',image());self.assertTrue(self.s.frame('depth'))
    def test_freshness_checked_before_cached_frame(self):
        self.s.ingest('depth',image());self.s.frame('depth');self.now+=3
        with self.assertRaises(ValueError):self.s.frame('depth')
    def test_pixel_matches_displayed_frame(self):
        self.s.ingest('depth',image());self.s.frame('depth')
        self.assertEqual(self.s.pixel(0,0,100)['source_stamp'],100)
        with self.assertRaises(ValueError):self.s.pixel(0,0,99)


def info_with_stamp():
    i=info();i.header.stamp=N(sec=100,nanosec=0);return i


if __name__=='__main__':unittest.main()
