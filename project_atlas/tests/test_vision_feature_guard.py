import io,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import atlas_vision_feature_guard as guard


class GuardTests(unittest.TestCase):
    def fixture(self):
        return {'ros':{k:{'age':0,'value':{'link_state':'LIVE','packet_fresh':True,'packet_age_s':0,'encoder_interval_delta_m':[0,0,0,0]}} for k in ('control_policy','cmd_vel','encoder_health')}}
    def call(self,data,temp=60,window=1):
        with patch.object(guard,'check',return_value=dict(cpu_percent=60,ram_percent=50,thermal_c={'cpu':temp},policy={'stop_latched':True})),patch.object(guard.urllib.request,'urlopen',return_value=io.BytesIO(json.dumps(data).encode())):
            return guard.observe(60,window)
    def test_safe(self):self.assertTrue(self.call(self.fixture())['telemetry_live'])
    def test_missing_stale_and_movement(self):
        for key in ('control_policy','cmd_vel','encoder_health'):
            for bad in (None,True,1.1,float('nan')):
                j=self.fixture();j['ros'][key]['age']=bad
                with self.assertRaises(ValueError):self.call(j)
        j=self.fixture();j['ros']['encoder_health']['value']['encoder_interval_delta_m']=[0,0,0,.01]
        with self.assertRaises(ValueError):self.call(j)
    def test_boundaries(self):
        for temp in (0,70,71,float('nan')):
            with self.assertRaises(ValueError):self.call(self.fixture(),temp=temp)
        for window in (.8,1.2,float('nan')):
            with self.assertRaises(ValueError):self.call(self.fixture(),window=window)
    def test_api_failure(self):
        with patch.object(guard.urllib.request,'urlopen',side_effect=TimeoutError('synthetic timeout')):
            with self.assertRaises(TimeoutError):guard.observe(60,1)

    def test_native_resource_reader_boundaries_offline(self):
        names=['cpu-thermal','gpu-thermal','soc0-thermal','soc1-thermal','soc2-thermal','tj-thermal']
        def read(path,*args,**kwargs):
            if str(path)=='/proc/meminfo':return 'MemTotal: 1000 kB\nMemAvailable: 500 kB\n'
            if path.name=='type':return names[int(path.parent.name[-1])]
            return '60000'
        zones=[Path('/synthetic/thermal_zone'+str(i)) for i in range(6)]
        with patch.object(guard,'validate_policy',return_value={}),patch.object(Path,'read_text',read),patch.object(Path,'glob',return_value=zones),patch.object(guard.subprocess,'check_output',return_value='ActiveState=inactive\nMainPID=0\n') as command:
            self.assertEqual(guard.check(60,{'ros':{},'system':{'ram_percent':50}})['ram_percent'],50)
            self.assertEqual(command.call_args.kwargs['timeout'],.3)
            with self.assertRaises(ValueError):guard.check(60,{'ros':{},'system':{'ram_percent':81}})
            with self.assertRaises(RuntimeError):guard.check(76,{'ros':{},'system':{'ram_percent':50}})
            command.side_effect=TimeoutError('systemctl timeout')
            with self.assertRaises(TimeoutError):guard.check(60,{'ros':{},'system':{'ram_percent':50}})


if __name__=='__main__':unittest.main()
