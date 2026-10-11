"""Prepare isolated config and collect installed-controller results, not live commands."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import resource
import yaml

p=argparse.ArgumentParser()
p.add_argument('--config',type=Path,required=True)
p.add_argument('--binary',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--inflation-factor',type=float)
a=p.parse_args()
if a.output.exists(): raise SystemExit('Use a new output directory')
a.output.mkdir(parents=True)
config=yaml.safe_load(a.config.read_text())
config={k:config[k] for k in ('controller_server','local_costmap')}
if a.inflation_factor is not None:
    config['controller_server']['ros__parameters']['FollowPath']['inflation_cost_scaling_factor']=a.inflation_factor
# Inject finite observations directly, no live ROS sensor subscriptions.
config['local_costmap']['local_costmap']['ros__parameters']['obstacle_layer']['observation_sources']=''
test_config=a.output/'isolated.yaml'
test_config.write_text(yaml.safe_dump(config))
env=dict(os.environ,ROS_DOMAIN_ID='173',ROS_LOCALHOST_ONLY='1',ROS_LOG_DIR=str(a.output/'roslogs'))
start=time.monotonic()
before=resource.getrusage(resource.RUSAGE_CHILDREN)
peak_rss=0
# Files avoid pipe backpressure; per-child /proc avoids inherited wait4 maxima.
with (a.output/'stdout.txt').open('w') as stdout,(a.output/'stderr.txt').open('w') as stderr:
    child=subprocess.Popen([str(a.binary.resolve()),'--ros-args','--params-file',str(test_config)],env=env,stdout=stdout,stderr=stderr)
    while child.poll() is None:
        if time.monotonic()-start>50:
            child.kill();child.wait();raise TimeoutError('bounded probe timed out')
        try:
            status=Path(f'/proc/{child.pid}/status').read_text()
            peak_rss=max(peak_rss,next(int(s.split()[1]) for s in status.splitlines() if s.startswith('VmRSS:')))
        except (FileNotFoundError,ProcessLookupError,StopIteration):pass
        time.sleep(.01)
after=resource.getrusage(resource.RUSAGE_CHILDREN)
rows=[s for s in (a.output/'stdout.txt').read_text().splitlines() if s.startswith('RESULT ')]
expected={'clear_straight':'COMMAND','clear_left':'COMMAND','clear_right':'COMMAND',
 'front_right_051_straight':'COMMAND','obstacle_appears':'REJECT',
 'obstacle_ray_cleared':'COMMAND','left_corner_curve':'REJECT','right_corner_curve':'REJECT',
 'rear_occupied':'REJECT','rear_unknown_encoded':'REJECT'}
actual={s.split()[1]:s.split()[2] for s in rows}
passed={name:actual.get(name)==value for name,value in expected.items()}
commands={s.split()[1]:float(s.split()[3]) for s in rows if len(s.split())>3 and s.split()[2]=='COMMAND'}
passed['dynamic_inflation_update']=commands.get('dynamic_factor_3',0)>commands.get('dynamic_factor_15',1)
report=dict(returncode=child.returncode,wall_s=time.monotonic()-start,results=rows,
 geometry_assertions=passed,
 resources=dict(cpu_s=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
 sampled_peak_rss_kib=peak_rss),
 limitations=['Static TF; no drivetrain dynamics','Injected observations, not DDS LaserScan delivery',
 'Controller plugin call, not BT/controller-server action lifecycle'])
(a.output/'result.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
raise SystemExit(child.returncode or (0 if all(passed.values()) else 1))
