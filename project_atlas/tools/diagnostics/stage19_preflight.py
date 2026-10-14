"""Read-only host preflight and exact input identities; no ROS/control writes."""
import json
import hashlib
import os
from pathlib import Path
import urllib.request

if __name__=='__main__':
    d=json.load(urllib.request.urlopen('http://127.0.0.1:8088/api/status',timeout=8))
    r=d.get('ros',{})
    def item(name):
        v=r.get(name,{}).get('value')
        if isinstance(v,str):
            try:return json.loads(v)
            except ValueError:return v
        return v
    policy=item('control_policy');cmd=item('cmd_vel')
    print(json.dumps({'policy':policy,'cmd_vel':cmd,'system':d.get('system',{}),
        'host_net_ns':os.readlink('/proc/self/ns/net'),'host_pid_ns':os.readlink('/proc/self/ns/pid')},indent=2))
    if not isinstance(policy,dict) or policy.get('stop_latched') is not True:
        raise SystemExit('Refuse native resource trial: production stop not observed latched')
    if not isinstance(cmd,dict) or cmd.get('lin')!=0 or cmd.get('ang')!=0:
        raise SystemExit('Refuse native resource trial: production movement not observed zero')
