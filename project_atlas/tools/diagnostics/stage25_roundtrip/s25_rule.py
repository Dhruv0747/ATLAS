import json,numpy as np
from s25_load import load
d=load({'/atlas/encoder_update','/atlas/encoder_health','/odom'})
enc=[(t,json.loads(m.data)) for t,m,_ in d['/atlas/encoder_update']]
et=np.array([t for t,_ in enc]); W=np.array([e['wheel_distances_m'] for _,e in enc])
hs=[(t,json.loads(m.data)) for t,m,_ in d['/atlas/encoder_health']]; ht=np.array([t for t,_ in hs])
ot=np.array([t for t,_,_ in d['/odom']]); ov=np.array([abs(m.twist.twist.linear.x) for _,m,_ in d['/odom']]); ow=np.array([abs(m.twist.twist.angular.z) for _,m,_ in d['/odom']])
# ground truth: wheel counted within the last 0.6 s window (any wheel moved >0.002 m in the preceding 0.6 s)
def truth(t):
    m=(et<=t)&(et>t-0.6); 
    if m.sum()<2: return False
    return np.abs(np.diff(W[m],axis=0)).max()>0.002 if m.sum()>1 else False
rows=[]
for t,h in hs:
    age=np.array(h['last_change_age_s'],float); packet=h['packet_fresh']
    ev2=packet and (age<0.6).sum()>=2
    ev1=packet and (age<0.6).sum()>=1
    i=max(np.searchsorted(ot,t)-1,0); odom_says_moving=ov[i]>0.01 or ow[i]>0.02
    rows.append((t,truth(t),ev1,ev2,odom_says_moving,h['consensus_state']))
R=np.array([(a,b,c,e,f) for _,a,b,c,e,f in [(0,)+r[1:5]+(0,) for r in rows]],dtype=bool) if False else None
T=np.array([r[1] for r in rows]);E1=np.array([r[2] for r in rows]);E2=np.array([r[3] for r in rows]);O=np.array([r[4] for r in rows])
def rep(name,P): print('%-34s moving-truth n=%d caught=%d (%.0f%%) | still n=%d false-flag=%d (%.1f%%)'%(name,T.sum(),(P&T).sum(),100*(P&T).sum()/T.sum(),(~T).sum(),(P&~T).sum(),100*(P&~T).sum()/(~T).sum()))
rep('current: odom vx>0.01|wz>0.02',O); rep('proposed A: >=1 wheel age<0.6s',E1); rep('proposed B: >=2 wheels age<0.6s',E2); rep('combined: odom OR >=2 wheels',O|E2)
# stationary reference windows (start 0-8 s, end after 430s)
t0=et[0]
for name,(a,b) in {'start still 0-8s':(0,8),'end still 436-450s':(436,450),'hall still 60-125 (no data)':(None,None)}.items():
    if a is None: continue
    m=np.array([a<=r[0]-t0<b for r in rows]); print(name,'n',m.sum(),'flag B',int((E2&m).sum()),'flag A',int((E1&m).sum()),'odom',int((O&m).sum()))
