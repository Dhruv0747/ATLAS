import copy,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from stage20_activation_evidence import Journal,Refused,revoke_owned

def valid():
 return {'utc':'2026-10-14T00:00:00Z','cpu_method':'/proc/stat','cpu_samples':[{'percent':70,'interval_s':1.01}],
 'dashboard_cpu':70,'dashboard_resource_age_s':None,'ram_percent':70,'temperature_c':59,
 'free_bytes':3*1024**3,'policy_age':.1,'command_age':.1,
 'policy':{'stop_latched':True,'source':'STOPPED','commission_armed':False},
 'command':{'lin':0,'ang':0},'missing_sensors':[],'authorization_valid':True}

class ActivationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.terminal=io.StringIO();self.j=Journal(self.tmp.name,self.terminal)
  self.addCleanup(lambda:self.j.stream.close() if not self.j.stream.closed else None)
 def reject(self,s,field):
  with self.assertRaises(Refused):self.j.admission(lambda:s)
  rows=[json.loads(x) for x in self.j.path.read_text().splitlines()]
  self.assertEqual(rows[0]['event'],'measurement');self.assertEqual(rows[0]['sample'],s)
  self.assertEqual(rows[-1]['failed_field'],field)
  self.assertIn('Traceback',rows[-1]['traceback'])
  self.assertFalse(rows[-1]['grant_created']);self.assertFalse(rows[-1]['collector_started'])
 def test_cpu(self):
  s=valid();s['cpu_samples'][0]['percent']=77.123;self.reject(s,'cpu_samples[0]')
 def test_cached_cpu(self):
  s=valid();s['dashboard_cpu']=81.2;self.reject(s,'dashboard_cpu')
 def test_ram(self):
  s=valid();s['ram_percent']=81;self.reject(s,'ram_percent')
 def test_temperature(self):
  s=valid();s['temperature_c']=71;self.reject(s,'temperature_c')
 def test_disk(self):
  s=valid();s['free_bytes']=100;self.reject(s,'free_bytes')
 def test_stale(self):
  s=valid();s['policy_age']=3;self.reject(s,'policy_age')
 def test_stop(self):
  s=valid();s['policy']['stop_latched']=False;self.reject(s,'stop_latched')
 def test_command(self):
  s=valid();s['command']['lin']=.1;self.reject(s,'command.lin')
 def test_sensors(self):
  s=valid();s['missing_sensors']=['/scan'];self.reject(s,'missing_sensors')
 def test_authorization_missing(self):
  s=valid();s.pop('authorization_valid');self.reject(s,'authorization_valid')
 def test_authorization_invalid(self):
  s=valid();s['authorization_valid']=False;self.reject(s,'authorization_valid')
 def test_valid_no_hardware(self):
  self.assertTrue(self.j.admission(valid)['admitted']);self.assertFalse(self.j.flags['collector_started'])
 def test_write_failure_fallback(self):
  s=valid();s['dashboard_cpu']=91
  with patch('stage20_activation_evidence.os.fsync',side_effect=OSError('disk full')):
   with self.assertRaises(OSError):self.j.admission(lambda:s)
  self.assertIn('91',self.terminal.getvalue());self.assertIn('evidence_write_failed',self.terminal.getvalue())
 def test_final_report_failure(self):
  with patch.object(Path,'open',side_effect=OSError('report failed')):
   r=self.j.finalize({'primary_error':'original refusal'})
  self.assertEqual(r['primary_error'],'original refusal');self.assertIn('final_report_failed',self.terminal.getvalue())
  self.assertIn('original refusal',self.j.path.read_text())
 def test_final_observer_cannot_mask(self):
  def fail():raise ValueError('secondary resource refusal')
  r=self.j.finalize({'primary_error':'first refusal'},{'safety':fail})
  self.assertEqual(r['primary_error'],'first refusal');self.assertTrue(r['safety']['unavailable'])
 def test_unique_sanitized(self):
  other=Journal(self.tmp.name,self.terminal);self.assertNotEqual(other.path,self.j.path);other.stream.close()
  self.j.write('output',stdout='password=secret123',stderr='Bearer private123')
  text=self.j.path.read_text();self.assertNotIn('secret123',text);self.assertNotIn('private123',text)
 def test_partial_owned_grant_cleanup(self):
  p=Path(self.tmp.name)/'grant';p.write_text('{partial');st=p.stat()
  with self.assertRaises(OSError):
   revoke_owned(p,(st.st_dev,st.st_ino),lambda p:(_ for _ in ()).throw(OSError('archive failed')))
  self.assertFalse(p.exists())
 def test_unrelated_grant_preserved(self):
  p=Path(self.tmp.name)/'other';p.write_text('unrelated')
  with self.assertRaises(ValueError):revoke_owned(p,(-1,-1),lambda p:None)
  self.assertEqual(p.read_text(),'unrelated')

if __name__=='__main__':unittest.main()
