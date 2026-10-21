import json,math,numpy as np,collections
from s25_load import load
d=load({'/atlas/encoder_update','/atlas/encoder_health','/steering/mode','/steering/front_angle_deg','/steering/rear_angle_deg','/yahboom/encoder/m1','/yahboom/encoder/m2','/yahboom/encoder/m3','/yahboom/encoder/m4','/cmd_vel_joy','/cmd_vel','/yahboom/odom'})
t0=d['/atlas/encoder_update'][0][0]
enc=[(t,json.loads(m.data)) for t,m,_ in d['/atlas/encoder_update']]
print('encoder_update keys:',list(enc[0][1].keys()))
# raw counts per channel overall
rc=np.array([e['raw_counts'] for _,e in enc]); et=np.array([t for t,_ in enc])
print('raw count span per channel (first,last,min,max):')
for i in range(4): print(' M%d'%(i+1),rc[0,i],rc[-1,i],rc[:,i].min(),rc[:,i].max(),'n changes',int((np.diff(rc[:,i])!=0).sum()))
# per phase count deltas
def phase(a,b,name):
    m=(et>=t0+a)&(et<t0+b)
    if m.sum()>1: print(name,'dcounts',(rc[m][-1]-rc[m][0]).tolist(),'dist',np.round(np.array([e['wheel_distances_m'] for (_,e),k in zip(enc,m) if k])[[-1]]-np.array([e['wheel_distances_m'] for (_,e),k in zip(enc,m) if k])[[0]],2).tolist())
phase(8,60,'outbound'); phase(125,172,'return1'); phase(195,450,'return2')
# health during return
eh=[(t,json.loads(m.data)) for t,m,_ in d['/atlas/encoder_health']]
print('health keys:',list(eh[0][1].keys()))
cs=collections.Counter(); 
for t,h in eh: cs[(h['consensus_state'],tuple(h['consensus_rejected_encoders']),tuple(h['selected_encoders']),tuple(h['excluded_encoders']),h['state'],h['link_state'])]+=1
for k,v in cs.most_common(12): print(v,k)
