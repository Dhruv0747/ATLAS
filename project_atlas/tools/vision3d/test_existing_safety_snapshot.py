import tempfile
import time
import unittest
from pathlib import Path
from existing_safety_snapshot import publish,verify

def observations(t):
    return {'policy':[{'stop_latched':True,'manual_only':True,'commission_armed':False,'source':'STOPPED'},t],
            'command':[[0.0]*6,t],
            'encoders':[{'packet_fresh':True,'link_state':'LIVE','packet_age_s':.01,'encoder_interval_delta_m':[0]*4},t]}

class CacheTests(unittest.TestCase):
    def test_safe_and_failure_paths(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state.json';values=observations(10);publish(p,values,10,'boot')
            self.assertTrue(verify(p,10.1,'boot')['safe'])
            for now,boot in [(11,'boot'),(10.1,'wrong'),(9,'boot')]:
                with self.assertRaises(ValueError):verify(p,now,boot)
            for key,bad in [('command',[[0,1,0,0,0,0],10]),('policy',[{},10]),('encoders',[{},10])]:
                values=observations(10);values[key]=bad;publish(p,values,10,'boot')
                with self.assertRaises(ValueError):verify(p,10.1,'boot')
    def test_republishing_does_not_refresh_source(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'s';publish(p,observations(8),10,'boot')
            with self.assertRaises(ValueError):verify(p,10.1,'boot')
    def test_missing_malformed_and_zero_motion(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'s'
            with self.assertRaises(OSError):verify(p,10,'boot')
            p.write_text('broken')
            with self.assertRaises(ValueError):verify(p,10,'boot')
            values=observations(10);values['encoders'][0]['encoder_interval_delta_m'][2]=.01;publish(p,values,10,'boot')
            with self.assertRaises(ValueError):verify(p,10.1,'boot')
    def test_native_file_cost(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'s';start=time.process_time()
            for _ in range(1000):
                now=time.monotonic();publish(p,observations(now),now,'boot');verify(p,time.monotonic(),'boot')
            print('IPC_1000_WRITE_READ_CPU_SECONDS',time.process_time()-start)

if __name__=='__main__':unittest.main()
import ast
import json
from unittest.mock import patch
from existing_safety_snapshot import Producer, Consumer

class IntegrationTests(unittest.TestCase):
    def test_http_down_and_latched_producer_crash(self):
        with tempfile.TemporaryDirectory() as d, patch('socket.socket', side_effect=AssertionError('network prohibited')):
            p=Path(d)/'state'; producer=Producer(p,'boot')
            for key,(value,stamp) in observations(10).items():producer.receive(key,value,stamp)
            producer.receive('command',[0]*6,10.11)
            consumer=Consumer(p,'boot')
            self.assertTrue(consumer.check(10.12)['safe'])
            with self.assertRaises(ValueError):consumer.check(11)
            publish(p,observations(11),11,'boot')
            with self.assertRaises(ValueError):consumer.check(11.01)

    def test_atomic_write_failure_invalidates(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state';publish(p,observations(10),10,'boot')
            producer=Producer(p,'boot')
            with patch('existing_safety_snapshot.os.replace',side_effect=OSError('disk failure')):
                producer.receive('command',[0]*6,10)
            self.assertTrue(producer.failed)
            self.assertFalse(p.exists())
            producer.receive('command',[0]*6,11)
            self.assertFalse(p.exists())

    def test_actual_recovery_callbacks_export_raw_values(self):
        source=Path(__file__).resolve().parents[2]/'scripts/atlas_sensor_recovery.py'
        tree=ast.parse(source.read_text()); methods={}
        names={'snapshot_observation','on_velocity','on_control_policy','on_message'}
        for node in ast.walk(tree):
            if isinstance(node,ast.FunctionDef) and node.name in names:methods[node.name]=node
        import math
        class String:
            def __init__(self,data):self.data=data
        ns={'time':time,'json':json,'math':math,'String':String,'MAX_STATUS_CHARS':8192,'STOP_COMMAND_MAX_AGE':1,'ATTEMPT_WINDOW':60}
        exec(compile(ast.Module(body=list(methods.values()),type_ignores=[]),'<callbacks>','exec'),ns)
        class Sink:
            def __init__(self):self.values={}
            def receive(self,k,v,t):self.values[k]=[v,t]
        class Host:pass
        h=Host();h.safety_snapshot=Sink();h.motion_last_seen=None;h.last_seen={};h.last_value={};h.attempts={'encoder_health':[]}
        for name in names:setattr(Host,name,ns[name])
        from types import SimpleNamespace as N
        h.on_velocity(N(linear=N(x=0,y=0,z=.001),angular=N(x=0,y=0,z=0)))
        self.assertEqual(h.safety_snapshot.values['command'][0][2],.001)
        h.on_control_policy(String(json.dumps(observations(10)['policy'][0])))
        self.assertTrue(h.safety_snapshot.values['policy'][0]['manual_only'])
        h.on_message('encoder_health',String(json.dumps(observations(10)['encoders'][0])))
        self.assertEqual(h.safety_snapshot.values['encoders'][0]['encoder_interval_delta_m'],[0]*4)
        h.on_control_policy(String('broken'))
        self.assertIsNone(h.safety_snapshot.values['policy'][0])

    def test_supervisor_does_not_launch_ros_observer(self):
        source=Path(__file__).with_name('web_activation_supervisor.py').read_text()
        self.assertNotIn('subprocess.Popen',source)
        self.assertIn('consumer.check(time.monotonic())',source)
