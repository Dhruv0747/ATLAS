import sys,copy
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tools/vision3d')]
from existing_safety_snapshot import SourceConsumer
from atlas_source_provenance import Provenance

def evidence():
 p={'source_provenance':dict(boot_id='b',pid=1,start_ticks=2,sequence=1,observed_mono=10.),'manual_only':True,'commission_armed':False,'stop_latched':True,'source':'STOPPED','published_command':dict(values=[0]*6,published_mono=10.,sequence=1)}
 e={'source_provenance':dict(boot_id='b',pid=3,start_ticks=4,sequence=1,observed_mono=10.),'encoder_packet_monotonic':9.9,'encoder_update_sequence':10,'packet_age_s':.1,'packet_fresh':True,'link_state':'LIVE','encoder_interval_delta_m':[0]*4}
 return p,e

def consumer():return SourceConsumer('b',{'policy':('b',1,2),'encoders':('b',3,4)})

def test_fresh_and_expiry():
 c=consumer();p,e=evidence();c.receive('policy',p,10);c.receive('encoders',e,10)
 assert c.check(10.2,10.1)['safe']
 with pytest.raises(ValueError):c.check(11.01,11)

@pytest.mark.parametrize('kind',['wrongboot','wrongpid','old','future','missing','nan','command_old','nonzero','packet_old','combined','output_old','disconnect','replay','reorder'])
def test_fail_closed(kind):
 c=consumer();p,e=evidence()
 if kind=='wrongboot':p['source_provenance']['boot_id']='old'
 if kind=='wrongpid':p['source_provenance']['pid']=99
 if kind=='old':p['source_provenance']['observed_mono']=8
 if kind=='future':p['source_provenance']['observed_mono']=11
 if kind=='missing':del p['source_provenance']
 if kind=='nan':p['source_provenance']['observed_mono']=float('nan')
 if kind=='command_old':p['published_command']['published_mono']=8
 if kind=='nonzero':p['published_command']['values'][5]=.1
 if kind=='packet_old':e['encoder_packet_monotonic']=8
 if kind=='combined':e['packet_age_s']=2
 with pytest.raises(ValueError):
  c.receive('policy',p,10);c.receive('encoders',e,10)
  if kind=='disconnect':c.disconnect()
  if kind=='replay':c.receive('policy',p,10.1)
  if kind=='reorder':
   p=copy.deepcopy(p);p['source_provenance'].update(sequence=2,observed_mono=9.99);c.receive('policy',p,10.1)
  c.check(10.2,9.4 if kind=='output_old' else 10.1)
 with pytest.raises(ValueError):c.check(10.2,10.1)

def test_metadata_records_six_components_after_publish():
 from types import SimpleNamespace as S
 p=Provenance();m=S(linear=S(x=1,y=2,z=3),angular=S(x=4,y=5,z=6))
 p.sent(m,10);assert p.command==dict(values=[1,2,3,4,5,6],published_mono=10,sequence=1)
 p.sent(m,11);assert p.command['sequence']==2
 assert p.stamp(11)['pid']>0

def test_all_mux_publish_paths_instrumented():
 import ast
 s=(ROOT/'scripts/atlas_cmd_vel_mux.py').read_text();tree=ast.parse(s)
 calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and ast.unparse(n.func)=='self.output.publish']
 assert len(calls)==1
 assert 'self._publish_with_provenance(Twist())' in s

def test_encoder_metadata_preserves_original_age():
 s=(ROOT/'scripts/yahboom_base.py').read_text()
 assert "'encoder_packet_monotonic': self._encoder_packet_stamp" in s
 assert "'packet_age_s': round(max(0.0, now - self._encoder_packet_stamp), 3)" in s


def test_received_values_cannot_be_mutated():
 c=consumer();p,e=evidence();c.receive('policy',p,10);c.receive('encoders',e,10)
 p['published_command']['values'][0]=1;e['encoder_packet_monotonic']=0
 assert c.check(10.2,10.1)['safe']

@pytest.mark.parametrize('field,value',[('encoder_packet_monotonic',9.8),('encoder_update_sequence',9)])
def test_packet_regression(field,value):
 c=consumer();p,e=evidence();c.receive('encoders',e,10)
 e=copy.deepcopy(e);e['source_provenance'].update(sequence=2,observed_mono=10.1)
 e[field]=value;e['packet_age_s']=10.1-e['encoder_packet_monotonic']
 with pytest.raises(ValueError):c.receive('encoders',e,10.1)

def test_exact_age_boundaries():
 c=consumer();p,e=evidence();e['encoder_packet_monotonic']=10.;e['packet_age_s']=0
 c.receive('policy',p,10);c.receive('encoders',e,10)
 assert c.check(11.,10.25)['safe']
 with pytest.raises(ValueError):c.check(11.00001,10.25)
