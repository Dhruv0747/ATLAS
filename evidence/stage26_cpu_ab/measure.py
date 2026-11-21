#!/usr/bin/env python3
"""Read-only CPU measurement window. usage: measure.py LABEL SECONDS OUT.json  (reads /proc only; no ROS, no writes except OUT)"""
import os, sys, time, json, subprocess, re
label, secs, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
CLK = os.sysconf('SC_CLK_TCK')
def svc_pid():
    return int(subprocess.check_output(['systemctl','--user','show','rover-status-web','-p','MainPID','--value']).decode().strip())
def pstat(pid):
    try:
        f = open(f'/proc/{pid}/stat').read(); r = f[f.rindex(')')+2:].split(); return int(r[11]) + int(r[12])
    except Exception: return None
def tstat(pid):
    d = {}
    try:
        for t in os.listdir(f'/proc/{pid}/task'):
            try:
                f = open(f'/proc/{pid}/task/{t}/stat').read(); r = f[f.rindex(')')+2:].split(); d[int(t)] = int(r[11]) + int(r[12])
            except Exception: pass
    except Exception: pass
    return d
def total():
    v = list(map(int, open('/proc/stat').readline().split()[1:])); return sum(v), v[3] + v[4]
def mem():
    m = {l.split(':')[0]: int(l.split()[1]) for l in open('/proc/meminfo')}; return m['MemAvailable']//1024
def rss(pid):
    try: return int(re.search(r'VmRSS:\s+(\d+)', open(f'/proc/{pid}/status').read()).group(1))//1024
    except Exception: return None
def temp(): return int(open('/sys/class/thermal/thermal_zone0/temp').read())/1000
PAT = re.compile(r'nav2|amcl|bt_navigator|controller_server|planner_server|map_server|lifecycle_manager|rf2o|ekf|rplidar|yahboom_base|cmd_vel_mux|camera|voice_companion|sensor_recovery|safety_status|atlas_status_web|foxglove|rosbridge|motion_recorder')
def procs():
    d = {}
    for p in os.listdir('/proc'):
        if p.isdigit():
            try:
                c = open(f'/proc/{p}/cmdline','rb').read().replace(b'\0', b' ').decode()[:120]
            except Exception: continue
            if PAT.search(c): d[int(p)] = c
    return d
pid = svc_pid(); P = procs(); P.setdefault(pid, 'status_web')
t0 = time.time(); T0 = total(); S0 = {p: pstat(p) for p in P}; TH0 = tstat(pid); sub = []; last = (t0, pstat(pid)); mems = []; temps = []; loads = []
while time.time() - t0 < secs:
    time.sleep(10); n = time.time(); s = pstat(pid)
    if s is not None and last[1] is not None: sub.append(round((s - last[1]) / CLK / (n - last[0]) * 100, 1))
    last = (n, s); mems.append(mem()); temps.append(temp()); loads.append(float(open('/proc/loadavg').read().split()[0]))
t1 = time.time(); T1 = total(); S1 = {p: pstat(p) for p in P}; TH1 = tstat(pid); dt = t1 - t0
ncpu = os.cpu_count()
res = dict(label=label, window_s=round(dt), ncpu=ncpu, status_web_pid=pid, status_web_age_s=round(time.time() - os.stat(f'/proc/{pid}').st_ctime),
  status_web_cpu_pct_of_core=round((S1[pid] - S0[pid]) / CLK / dt * 100, 1), status_web_subwindows_10s=sub,
  status_web_rss_mb=rss(pid), status_web_threads=len(TH1),
  total_cpu_busy_pct=round((1 - (T1[1] - T0[1]) / (T1[0] - T0[0])) * 100, 1),
  avail_mb_min=min(mems), avail_mb_max=max(mems), temp_c_max=max(temps), load1_mean=round(sum(loads)/len(loads), 1),
  threads_top=sorted(((tid, round((TH1[tid] - TH0.get(tid, 0)) / CLK / dt * 100, 1)) for tid in TH1), key=lambda x: -x[1])[:6],
  procs=sorted(((p, round((S1[p] - S0[p]) / CLK / dt * 100, 1), P[p][:70]) for p in P if S0.get(p) is not None and S1.get(p) is not None), key=lambda x: -x[1])[:14])
json.dump(res, open(out, 'w'), indent=1); print(json.dumps({k: v for k, v in res.items() if k not in ('procs',)}))
