"""PC/WSL only: profile imports/launch; never call worker, ROS init or hardware.

Run under a sourced ROS Humble environment, like the production web owner.
"""
import json,os,resource,statistics,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
assert os.environ.get('ROS_DISTRO')=='humble','source PC ROS Humble first'
env=dict(os.environ,PYTHONPATH=str(ROOT/'scripts')+':'+str(ROOT/'tools/vision3d')+':'+os.environ.get('PYTHONPATH',''))
code='import atlas_vision3d_runtime; import stationary_gate; import stationary_ros_probe'
cases={
 'python_empty':['/usr/bin/python3','-c','pass'],
 'runtime_import_only':['/usr/bin/python3','-c','import atlas_vision3d_runtime'],
 'imports_direct':['/usr/bin/python3','-c',code],
 'old_login_shell_ros_setup':['/bin/bash','-lc',"source /opt/ros/humble/setup.bash; exec /usr/bin/python3 -c '"+code+"'"],
}
rows=[]
for _ in range(7):
    for name,cmd in cases.items():
        before=resource.getrusage(resource.RUSAGE_CHILDREN);start=time.monotonic()
        subprocess.run(cmd,env=env,check=True,stdout=subprocess.DEVNULL,timeout=10)
        after=resource.getrusage(resource.RUSAGE_CHILDREN)
        rows.append({'case':name,'wall_s':time.monotonic()-start,'cpu_s':after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime})
summary={name:{key:statistics.median(r[key] for r in rows if r['case']==name) for key in ('cpu_s','wall_s')} for name in cases}
subprocess.run(['/usr/bin/python3','-c','import rclpy; import sensor_msgs.msg; import tf2_ros'],env=env,check=True,timeout=10)
print(json.dumps({'platform':'PC WSL, not Jetson','repetitions':7,'medians':summary,'inherited_ros_imports':'PASS; no rclpy.init','samples':rows},indent=2))
