"""Read-only timestamp exchange over an already authorized SSH account.

No clock changes, ROS imports or subscriptions. RTT bound assumes no local clock
step during each exchange. Remote timestamp is sampled between send and receipt.
"""
import argparse
import json
import subprocess
import threading
import queue
import time


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--ssh',required=True);p.add_argument('--key',required=True)
    p.add_argument('--host',required=True)
    a=p.parse_args()
    remote="python3 -u -c 'import sys,time; [(print(time.time_ns(),flush=True)) for x in sys.stdin]'"
    child=subprocess.Popen([a.ssh,'-T','-i',a.key,'-o','BatchMode=yes','-o','ConnectTimeout=5',a.host,remote],
                           stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
    lines=queue.Queue()
    def read():
        for line in child.stdout:lines.put(line)
    threading.Thread(target=read,daemon=True).start()
    rows=[]
    try:
        for i in range(6):
            t0=time.time_ns();m0=time.monotonic_ns()
            child.stdin.write('time\n');child.stdin.flush()
            remote_ns=int(lines.get(timeout=8).strip())
            t1=time.time_ns();m1=time.monotonic_ns()
            rows.append({'index':i,'pc_start_ns':t0,'pc_end_ns':t1,'remote_ns':remote_ns,
                         'offset_ns':remote_ns-(t0+t1)//2,'uncertainty_ns':(m1-m0)//2,
                         'clock_step_residual_ns':(t1-t0)-(m1-m0),
                         'offset_lower_ns':remote_ns-t1,'offset_upper_ns':remote_ns-t0})
            if i<5:time.sleep(4)
    finally:
        child.stdin.close()
        try:child.wait(timeout=3)
        except subprocess.TimeoutExpired:child.kill();child.wait()
    print(json.dumps({'clock_host':'calling_PC_runtime','samples':rows,'no_clock_changes':True,
                     'source_headers_observed':False,'precise_sensor_latency_verified':False},indent=2))


if __name__=='__main__':main()
