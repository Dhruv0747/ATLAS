import sqlite3,glob,json,numpy as np
B='/mnt/user-data/uploads/Downloads/atlas_stage25_bags/bags_work/'
print('--- manifests')
for f in sorted(glob.glob(B+'*/atlas_capture_manifest.json')):
    m=json.load(open(f)); print(f.split('/')[-2][8:30],'reason',m['reason'],'start',m['started_utc'],'closed',m['closed_utc'],'dropped',m['dropped'],'middleware',m['middleware_drops'],'bytes',m['bag_bytes'])
h=json.load(open(B+'recorder_health.json')); print('health: middleware_events',h['middleware_events'],'dropped',h['dropped'],'missing',h['missing'],'stale',h['stale'],'state',h['state'])
req=['/scan','/scan_raw','/yahboom/odom','/odom','/amcl_pose','/atlas/encoder_update','/atlas/control_policy','/im10a/imu/bias_corrected_candidate','/cmd_vel','/joy','/tf','/yahboom/encoder/m1','/yahboom/encoder/m2','/yahboom/encoder/m3','/yahboom/encoder/m4','/particle_cloud','/lidar/odom']
seen={}
for f in sorted(glob.glob(B+'*/*.db3')):
    c=sqlite3.connect('file:'+f+'?mode=ro',uri=True); tp={i:n for i,n in c.execute('select id,name from topics')}
    for tid,t in c.execute('select topic_id,timestamp from messages order by timestamp'): seen.setdefault(tp[tid],set()).add(t)
print('--- per-topic totals (deduped) and largest gap inside a capture (>1.0 s excluded when between captures)')
caps=[]
for f in sorted(glob.glob(B+'*/*.db3')):
    c=sqlite3.connect('file:'+f+'?mode=ro',uri=True); mm=c.execute('select min(timestamp),max(timestamp) from messages').fetchone(); caps.append((mm[0]/1e9,mm[1]/1e9))
for tpc in req:
    ts=np.array(sorted(seen.get(tpc,[])))/1e9
    if len(ts)<2: print('%-40s n=%d'%(tpc,len(ts))); continue
    g=np.diff(ts); inside=[x for x,a,b in zip(g,ts[:-1],ts[1:]) if any(s<=a and b<=e for s,e in caps)]
    print('%-40s n=%6d  median dt %.3f s  max intra-capture gap %.2f s'%(tpc,len(ts),np.median(g),max(inside) if inside else 0))
