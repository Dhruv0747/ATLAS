#!/usr/bin/env python3
"""One bounded read-only CHECK MY LOCATION request and resource measurement.

Never releases stop or publishes pose/velocity. Existing server enforces gates.
All evidence remains in a caller-selected new private output file.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',required=True,type=Path)
    a=p.parse_args()
    if a.out.exists():p.error('preserve existing evidence')
    pid=int(subprocess.check_output(['systemctl','--user','show','atlas-localization-monitor','-p','MainPID','--value']))
    def process():
        fields=Path('/proc/%d/stat'%pid).read_text().rsplit(')',1)[1].split()
        return time.monotonic(),(int(fields[11])+int(fields[12]))/os.sysconf('SC_CLK_TCK'),int(fields[21])*os.sysconf('SC_PAGE_SIZE')
    def http(route,body=None):
        request=urllib.request.Request('http://127.0.0.1:8088'+route,
            data=None if body is None else json.dumps(body).encode(),
            headers={'Origin':'http://127.0.0.1:8088','X-Atlas-Location':'1','Content-Type':'application/json'})
        started=time.monotonic()
        try:
            response=urllib.request.urlopen(request,timeout=4)
        except urllib.error.HTTPError as exc:response=exc
        with response:return response.code,json.loads(response.read()),time.monotonic()-started
    before=process();samples=[before];latencies=[];dashboard_during=[]
    code,reply,latency=http('/api/location-check',{'action':'start'})
    request_id=reply.get('request_id');final=reply
    while reply.get('accepted') and time.monotonic()-before[0]<35:
        time.sleep(.25);samples.append(process())
        _,state,dt=http('/api/location-check');latencies.append(dt)
        if len(latencies)%3==0:
            status_code,_,elapsed=http('/api/status')
            dashboard_during.append(dict(status=status_code,seconds=elapsed))
        if state.get('request_id')==request_id and state.get('state')!='CHECKING':final=state;break
    after=process()
    status_code,_,status_latency=http('/api/status')
    report=dict(http_code=code,ack_s=latency,reply=reply,final=final,pid=pid,
        wall_s=after[0]-before[0],cpu_s=after[1]-before[1],rss_before_mib=before[2]/2**20,
        rss_after_mib=after[2]/2**20,peak_rss_mib=max(v[2] for v in samples+[after])/2**20,
        peak_interval_cpu_one_core_percent=max([100*(b[1]-a[1])/(b[0]-a[0]) for a,b in zip(samples,samples[1:])] or [0]),
        status_http_code=status_code,status_http_s=status_latency,poll_max_s=max(latencies or [0]),
        dashboard_during=dashboard_during)
    with a.out.open('x') as stream:json.dump(report,stream,indent=2)
    a.out.chmod(0o600);print(json.dumps(report,indent=2))


if __name__=='__main__':main()
