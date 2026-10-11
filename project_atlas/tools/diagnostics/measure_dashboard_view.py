"""Finite parked HTTP workload; process CPU is percent of one core, not system."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

def proc(pid):
    s=Path('/proc/'+pid+'/stat').read_text().split(') ',1)[1].split()
    return (int(s[11])+int(s[12]))/os.sysconf('SC_CLK_TCK'),int(s[21])*os.sysconf('SC_PAGE_SIZE'),int(s[19])

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--endpoint',default='/api/lidar-view');p.add_argument('--hz',type=float,default=2);a=p.parse_args()
    if a.out.exists() or a.endpoint not in ('/api/lidar-view','/camera.jpg','/api/status') or not 0<a.hz<=8:p.error('new output, allowed endpoint and rate required')
    pid=subprocess.check_output(['systemctl','--user','show','rover-status-web','-p','MainPID','--value'],text=True).strip()
    before=proc(pid);start=time.monotonic();rows=[];peak=0;bytes_total=0
    while time.monotonic()-start<30:
        t=time.monotonic()
        try:
            with urllib.request.urlopen('http://127.0.0.1:8088'+a.endpoint,timeout=3) as r:body=r.read()
            bytes_total+=len(body);row=dict(ms=(time.monotonic()-t)*1000,bytes=len(body))
            if a.endpoint!='/camera.jpg':
                d=json.loads(body);row.update({k:d.get(k) for k in ('state','age_s','hz','valid','reason')})
            elif not a.out.with_suffix('.jpg').exists():a.out.with_suffix('.jpg').write_bytes(body)
        except Exception as e:row=dict(error=str(e))
        peak=max(peak,proc(pid)[1]);rows.append(row);time.sleep(max(0,1/a.hz-(time.monotonic()-t)))
    elapsed=time.monotonic()-start;after=proc(pid)
    cpu=100*(after[0]-before[0])/elapsed if after[2]==before[2] else None
    result=dict(endpoint=a.endpoint,seconds=elapsed,cpu_one_core=cpu,cpu_all_six=cpu/6 if cpu is not None else None,rss_peak_mib=peak/2**20,bytes=bytes_total,mbps=bytes_total*8/elapsed/1e6,requests=len(rows),errors=sum('error' in x for x in rows),rows=rows)
    a.out.write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='rows'}))
if __name__=='__main__':main()
