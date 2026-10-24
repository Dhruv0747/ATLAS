"""PC-only four-arm transient sandbox experiment; never connects to ATLAS."""
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import tempfile


def main():
    if platform.machine() != 'x86_64' or os.geteuid() != 0:
        raise RuntimeError('Requires isolated PC WSL root, not Jetson')
    script = Path(__file__).with_name('benchmark_localization_ros_startup.py').resolve()
    results = []
    for name, quota, udp in [('baseline',False,False),('quota',True,False),
                              ('udp',False,True),('quota_udp',True,True)]:
        home = tempfile.mkdtemp(prefix='atlas-scheduling-pc-')
        env = ['HOME='+home,'ROS_LOCALHOST_ONLY=1','ROS_DOMAIN_ID=214',
               'RMW_IMPLEMENTATION=rmw_fastrtps_cpp']
        if udp: env.append('FASTDDS_BUILTIN_TRANSPORTS=UDPv4')
        props = ['-p','PrivateNetwork=yes','-p','RuntimeMaxSec=30',
                 '-p','TimeoutStopSec=2','-p','KillMode=control-group']
        if quota: props += ['-p','CPUQuota=60%','-p','Nice=10']
        command = 'source /opt/ros/humble/setup.bash && exec '+shlex.join(
            ['/usr/bin/env',*env,'/usr/bin/python3','-B',str(script),'--child','original'])
        run = subprocess.run(['systemd-run','--wait','--pipe','--collect',*props,
                              '/bin/bash','-c',command], capture_output=True,text=True,timeout=40)
        if run.returncode:
            raise RuntimeError(run.stderr+run.stdout)  # no automatic retry
        data = json.loads(run.stdout)
        data['case'] = name
        data['runner_log'] = run.stderr
        results.append(data)
    print(json.dumps(results,indent=2))


if __name__ == '__main__': main()
