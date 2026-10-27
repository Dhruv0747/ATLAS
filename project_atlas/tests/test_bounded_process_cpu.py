import copy,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'tools/diagnostics'))
import bounded_process_cpu as p

def pair():
 a={'cpu':[100,0,0,100,0,0,0,0],'cpu_started':1.,'processes':{'7':{'start_ticks':10,'user_ticks':100,'system_ticks':0,'sample_started':1.}},'groups':{'g':{'inode':1,'device':1,'usage_ns':100,'sample_started':1.}}}
 b=copy.deepcopy(a);b['cpu']=[160,0,0,140,0,0,0,0];b['cpu_started']=2.;b['processes']['7'].update(user_ticks=120,sample_started=2.);b['groups']['g'].update(usage_ns=200000100,sample_started=2.)
 return a,b

def test_synchronized_deltas():
 a,b=pair();d=p.differences(a,b,100)
 assert d['cpu_pct']==60 and d['aggregate_interval_s']==1
 assert d['processes']['7']['one_core_pct']==20
 assert d['groups']['g']['one_core_pct']==20

def test_pid_reuse_excluded():
 a,b=pair();b['processes']['7']['start_ticks']=99
 d=p.differences(a,b,100);assert d['new_or_reused']==['7'] and not d['processes']

def test_exit_explicit():
 a,b=pair();b['processes']={};assert p.differences(a,b,100)['exited']==['7']

def test_group_recreated_excluded():
 a,b=pair();b['groups']['g']['inode']=2;assert not p.differences(a,b,100)['groups']

@pytest.mark.parametrize('counter',[0,3,4])
def test_counter_reset(counter):
 a,b=pair();b['cpu'][counter]=-1
 with pytest.raises(ValueError):p.differences(a,b,100)

def test_stat_name_spaces_and_parentheses():
 fields=['0']*30;fields[11]='10';fields[12]='2';fields[19]='999'
 d=p.process_stat('42 (a ) b) '+' '.join(fields));assert d['start_ticks']==999 and d['name']=='a ) b'

@pytest.mark.parametrize('cpu,ram,temp,failed',[(75,80,70,[]),(75.1,80,70,['cpu']),(50,81,60,['ram']),(50,20,71,['temperature'])])
def test_unchanged_limits(cpu,ram,temp,failed):
 r=p.resource_check(cpu,{'MemTotal':100,'MemAvailable':100-ram},{'thermal_zones_c':{'cpu':temp}})
 assert r['failed']==failed

@pytest.mark.parametrize('thermal',[{}, {'thermal_zones_c':{'x':None}},{'thermal_zones_c':{'x':float('nan')}}])
def test_missing_resource_blocks(thermal):
 with pytest.raises(ValueError):p.resource_check(20,{'MemTotal':100,'MemAvailable':90},thermal)

def test_cgroup_v1_v2_and_escape(tmp_path):
 mounts=[{'version':2,'root':'/','mount':str(tmp_path)}]
 assert p.group_path({'controllers':'','path':'/x'},mounts)==(2,tmp_path/'x')
 with pytest.raises(ValueError):p.group_path({'controllers':'','path':'/../escape'},mounts)
 mounts[0]['version']=1
 assert p.group_path({'controllers':'cpu,cpuacct','path':'/x'},mounts)[0]==1

def test_duration_and_no_overwrite(tmp_path):
 with pytest.raises(ValueError):p.run(tmp_path/'a',61)
 f=tmp_path/'a';f.write_text('preserve')
 with pytest.raises(FileExistsError):p.run(f,2,thermal_reader=lambda:{})
 assert f.read_text()=='preserve'

def test_abort_preserves_sample(tmp_path,monkeypatch):
 a,b=pair();a.update(errors=[]);b.update(errors=[]);b['cpu']=[199,0,0,101,0,0,0,0]
 seq=iter([a,b]);f=tmp_path/'out'
 monkeypatch.setattr(p.time,'sleep',lambda _:None)
 monkeypatch.setattr(p,'read',lambda _: 'MemTotal: 100 kB\nMemAvailable: 90 kB\n')
 with pytest.raises(ValueError,match='resource limit'):p.run(f,2,collect=lambda:next(seq),thermal_reader=lambda:{'thermal_zones_c':{'x':50}})
 text=f.read_text();assert '"cpu_pct": 99.0' in text and '"kind": "aborted"' in text

def test_snapshot_fixture(tmp_path):
 proc=tmp_path/'proc';proc.mkdir();(proc/'self').mkdir();cg=tmp_path/'cg';cg.mkdir();g=cg/'unit';g.mkdir()
 (g/'cpu.stat').write_text('usage_usec 123\nuser_usec 100\n')
 (proc/'self/mountinfo').write_text(f'1 0 0:1 / {cg} rw - cgroup2 cgroup rw\n')
 (proc/'stat').write_text('cpu 1 2 3 4 5 6 7 8\n')
 task=proc/'7';task.mkdir();fields=['0']*30;fields[19]='10';fields[11]='20'
 (task/'stat').write_text('7 (test) '+' '.join(fields));(task/'cgroup').write_text('0::/unit\n')
 s=p.snapshot(proc)
 assert not s['errors'] and s['groups'][str(g)]['usage_ns']==123000
 assert s['processes']['7']['user_ticks']==20
 assert s['finished']>=s['started']

def test_unreadable_baseline_stops(tmp_path):
 with pytest.raises(ValueError,match='incomplete baseline'):
  p.run(tmp_path/'out',2,collect=lambda:{'errors':[{'error_type':'PermissionError'}]},thermal_reader=lambda:{})
 assert 'PermissionError' in (tmp_path/'out').read_text()
