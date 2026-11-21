import json,numpy as np
from s25_load import load
d=load({'/atlas/encoder_update'})
t0=d['/atlas/encoder_update'][0][0]
enc=[(t,json.loads(m.data)) for t,m,_ in d['/atlas/encoder_update']]
et=np.array([t for t,_ in enc]); W=np.array([e['wheel_distances_m'] for _,e in enc]); R=np.array([e['raw_counts'] for _,e in enc])
dW=np.diff(W,axis=0); dt=np.diff(et); keep=dt<0.5
both=(dW[:,0]>0.003)&(dW[:,3]>0.003)&keep
v=(dW[:,0]+dW[:,3])/2/np.maximum(dt,1e-3)
phase=np.where(et[1:]-t0<60,'outbound',np.where(et[1:]-t0<180,'return1','return2'))
for ph in ('outbound','return1','return2'):
    m=both&(phase==ph)
    print(ph,'M1&M4 fwd intervals',int(m.sum()),'M2 opposite(<-0.002)',int((m&(dW[:,1]<-0.002)).sum()),'M2 ~0',int((m&(np.abs(dW[:,1])<=0.002)).sum()),'M2 same',int((m&(dW[:,1]>0.002)).sum()),'M3 ~0',int((m&(np.abs(dW[:,2])<=0.002)).sum()))
m=both&(phase!='outbound')
for lo,hi in ((0,.06),(.06,.12),(.12,.2),(.2,.4)):
    s=m&(v>=lo)&(v<hi); print('return, wheel speed %.2f-%.2f m/s: n=%d  M2 opposite %d  M2 same %d'%(lo,hi,s.sum(),(s&(dW[:,1]<-0.002)).sum(),(s&(dW[:,1]>0.002)).sum()))
m=both&(phase=='outbound')
for lo,hi in ((0,.06),(.06,.12),(.12,.2),(.2,.5)):
    s=m&(v>=lo)&(v<hi); print('outbound, speed %.2f-%.2f: n=%d  M2 opposite %d  M2 same %d'%(lo,hi,s.sum(),(s&(dW[:,1]<-0.002)).sum(),(s&(dW[:,1]>0.002)).sum()))
# first sign change of M2 relative to M1 in time
sgn=np.sign(dW[:,1])*np.sign(dW[:,0])
idx=[i for i in np.where(both)[0]]
# time series of M2 cumulative vs M1 cumulative at coarse steps (every 10s)
for a in range(0,450,30):
    mm=(et-t0>=a)&(et-t0<a+30)
    if mm.sum()>2: w=W[mm]; print(a,'M1 %+.2f M2 %+.2f M3 %+.2f M4 %+.2f'%tuple(w[-1]-w[0]))
