import json,numpy as np
from s25_load import load
d=load({'/atlas/encoder_health','/yahboom/odom','/odom'})
t0=d['/atlas/encoder_health'][0][0]
H=[(t,json.loads(m.data)) for t,m,_ in d['/atlas/encoder_health']]; ht=np.array([t for t,_ in H])
O=[(t,m) for t,m,_ in d['/odom']]; ot=np.array([t for t,_ in O])
frames=[]
def pick(rel,label,expect):
    i=int(np.abs(ht-(t0+rel)).argmin()); t,h=H[i]; j=int(np.abs(ot-t).argmin()); om=O[j][1]
    keep={k:h[k] for k in ('state','consensus_state','consensus_rejected_encoders','packet_fresh','last_change_age_s','encoder_interval_delta_m')}
    frames.append({'label':label,'source_bag_time_s':round(t-t0,2),'expect':expect,
      'odom':{'age':0.1,'value':{'vx':om.twist.twist.linear.x,'wz':om.twist.twist.angular.z}},
      'encoder_health':{'age':0.2,'value':json.dumps(keep)}})
pick(3,'rest at start, nothing counted','Stopped')
pick(20.0,'outbound, odometry tracking','Moving')
pick(253.95,'slow return burst, M2 reversed/M3 dead, consensus UNAVAILABLE, odom ~0','Moving · odometry not tracking')
pick(397.4,'slow return burst, consensus UNAVAILABLE, odom 0','Moving · odometry not tracking')
# pick the first recorded frame after 300 s where odometry is exactly in the blind regime
for i,(t,h) in enumerate(H):
    if t-t0>300:
        j=int(np.abs(ot-t).argmin()); om=O[j][1]
        if abs(om.twist.twist.linear.x)<0.01 and abs(om.twist.twist.angular.z)<0.02 and sum(1 for a in h['last_change_age_s'] if a<0.6)>=3 and h['consensus_state']=='UNAVAILABLE':
            pick(t-t0,'slow burst, wheels counting, odom ~0, consensus UNAVAILABLE','Moving · odometry not tracking'); break
pick(445,'rest at end, nothing counted','Stopped')
json.dump({'provenance':'Stage 25 recording 2026-10-15 (bags capture_20261015T160704Z_5d3cfaf5 ... fe0d4344); values copied, not synthesised','frames':frames},open('stage25_motion_frames.json','w'),indent=1)
for f in frames: 
    h=json.loads(f['encoder_health']['value']); print(f['source_bag_time_s'],f['expect'],'odom',round(f['odom']['value']['vx'],3),'ages',h['last_change_age_s'],h['consensus_state'])
