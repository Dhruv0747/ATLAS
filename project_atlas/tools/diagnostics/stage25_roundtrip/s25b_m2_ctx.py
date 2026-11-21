import json,numpy as np,datetime as dt
from s25_load import load
d=load({'/atlas/encoder_update','/bms/voltage','/bms/status','/steering/front_angle_deg','/steering/rear_angle_deg','/steering/mode','/cmd_vel','/cmd_vel_joy'})
ist=lambda t: dt.datetime.fromtimestamp(t, dt.timezone(dt.timedelta(hours=5,minutes=30))).strftime('%H:%M:%S')
tf=dt.datetime(2026,10,16,21,40,24,tzinfo=dt.timezone(dt.timedelta(hours=5,minutes=30))) # placeholder date fixed below
enc=d['/atlas/encoder_update']; t0=enc[0][0]
# fault epoch = first row where M2 raw == -40584
for t,m,_ in enc:
    if json.loads(m.data)['raw_counts'][1]==-40584: tfe=t;break
print('fault epoch',ist(tfe))
v=[(t,m.data) for t,m,_ in d['/bms/voltage']]
bv=[json.loads(m.data)['voltage_v'] for t,m,_ in d['/bms/status']]; bi=[json.loads(m.data)['current_a'] for t,m,_ in d['/bms/status']]; print('BMS status n=%d V min/max %.1f/%.1f  I min/max %.1f/%.1f'%(len(bv),min(bv),max(bv),min(bi),max(bi)))
print('steering mode transitions:')
last=None
for t,m,_ in d['/steering/mode']:
    if m.data!=last: print(' ',ist(t),m.data); last=m.data
fa=np.array([(t,m.data) for t,m,_ in d['/steering/front_angle_deg']]); ra=np.array([(t,m.data) for t,m,_ in d['/steering/rear_angle_deg']])
for a,b,nm in ((0,60,'outbound'),(60,tfe-t0-4,'pre-fault return'),(tfe-t0+5,500,'post-fault')):
    m=(fa[:,0]-t0>=a)&(fa[:,0]-t0<b); m2=(ra[:,0]-t0>=a)&(ra[:,0]-t0<b); print(nm,'front angle min/max/mean %.1f %.1f %.1f'%(fa[m,1].min(),fa[m,1].max(),fa[m,1].mean()),'| rear %.1f %.1f %.1f'%(ra[m2,1].min(),ra[m2,1].max(),ra[m2,1].mean()))
# commanded direction around fault
cv=[(t,m.linear.x,m.angular.z) for t,m,_ in d['/cmd_vel']]
w=[(ist(t),round(x,2),round(z,2)) for t,x,z in cv if tfe-3<t<tfe+8]
print('cmd_vel near fault:',w[:12])
# regression slope M2 vs M1 (sign-corrected) on intervals where M1 and M4 agree
et=np.array([t for t,_,_ in enc]); R=np.array([json.loads(m.data)['raw_counts'] for _,m,_ in enc],float); S=np.array([json.loads(m.data)['encoder_signs'] for _,m,_ in enc])
dR=np.diff(R,axis=0)*S[1:]; dts=np.diff(et); ok=dts<0.5
def reg(nm,a,b,lo,hi):
    m=ok&(et[1:]>=a)&(et[1:]<b)&(dR[:,0]>lo)&(dR[:,0]<hi)&(dR[:,3]>0.6*dR[:,0])&(dR[:,3]<1.6*dR[:,0])
    if m.sum()<8: print(nm,'n',m.sum());return
    x=(dR[m,0]+dR[m,3])/2; y=dR[m,1]; k=np.polyfit(x,y,1); r=np.corrcoef(x,y)[0,1]
    print('%-34s n=%3d slope M2fwd/M1M4fwd %+.2f  r=%+.2f  frac M2 opposite %.2f frac M2==0 %.2f'%(nm,m.sum(),k[0],r,(y<-2).mean(),(np.abs(y)<=2).mean()))
for lo,hi in ((10,60),(60,400)):
    reg('pre-fault  M1 %d-%d counts'%(lo,hi),t0,tfe-4,lo,hi)
    reg('post-fault M1 %d-%d counts'%(lo,hi),tfe+5,et[-1]+1,lo,hi)
