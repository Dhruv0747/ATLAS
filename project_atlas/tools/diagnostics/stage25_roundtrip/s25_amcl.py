import json,math,numpy as np
from s25_load import load
d=load({'/amcl_pose','/lidar/odom','/atlas/encoder_update','/odom','/yahboom/odom'})
def yaw(q): return math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
t0=d['/amcl_pose'][0][0]
A=np.array([(t,m.pose.pose.position.x,m.pose.pose.position.y,yaw(m.pose.pose.orientation),math.sqrt(m.pose.covariance[0]),math.sqrt(m.pose.covariance[7]),math.degrees(math.sqrt(max(m.pose.covariance[35],0)))) for t,m,_ in d['/amcl_pose']])
L=np.array([(t,m.pose.pose.position.x,m.pose.pose.position.y,yaw(m.pose.pose.orientation)) for t,m,_ in d['/lidar/odom']])
enc=[(t,json.loads(m.data)) for t,m,_ in d['/atlas/encoder_update']]; et=np.array([t for t,_ in enc]); W=np.array([e['wheel_distances_m'] for _,e in enc])
Y=np.array([(t,m.pose.pose.position.x,m.pose.pose.position.y) for t,m,_ in d['/yahboom/odom']])
print('AMCL msgs',len(A),'rate %.2f Hz'%(len(A)/(A[-1,0]-A[0,0])))
print('--- AMCL steps >0.12 m between consecutive messages (rel t, dt, step m, dyaw°, wheel M1/M4 moved in that dt, lidar-odom step, std before->after)')
for i in range(1,len(A)):
    st=math.hypot(A[i,1]-A[i-1,1],A[i,2]-A[i-1,2]); dy=math.degrees((A[i,3]-A[i-1,3]+math.pi)%(2*math.pi)-math.pi)
    if st>0.12 or abs(dy)>12:
        m=(et>A[i-1,0])&(et<=A[i,0]); w=(W[m][-1]-W[m][0]) if m.sum()>1 else np.zeros(4)
        l0=np.interp(A[i-1,0],L[:,0],L[:,1]);l1=np.interp(A[i,0],L[:,0],L[:,1]);m0=np.interp(A[i-1,0],L[:,0],L[:,2]);m1=np.interp(A[i,0],L[:,0],L[:,2])
        gap=A[i,0]-A[i-1,0]
        print('%6.1f dt%5.1f step %.2f dyaw %+5.0f wheels M1 %.2f M4 %.2f | lidarStep %.2f | std %.2f->%.2f yawstd %.0f->%.0f'%(A[i,0]-t0,gap,st,dy,w[0],w[3],math.hypot(l1-l0,m1-m0),A[i-1,4],A[i,4],A[i-1,6],A[i,6]))
print('--- covariance extremes: max xy std %.2f at t=%.0f; max yaw std %.0f° at t=%.0f'%(A[:,4].max(),A[A[:,4].argmax(),0]-t0,A[:,6].max(),A[A[:,6].argmax(),0]-t0))
# relative-motion tracking: sample at 10 s, compare AMCL displacement magnitude vs lidar odom magnitude
print('--- 15 s windows: AMCL path vs lidar-odom path vs wheel(M1,M4 mean) vs yahboom path')
for a in range(10,450,15):
    mA=(A[:,0]>=t0+a)&(A[:,0]<t0+a+15); mL=(L[:,0]>=t0+a)&(L[:,0]<t0+a+15); mW=(et>=t0+a)&(et<t0+a+15); mY=(Y[:,0]>=t0+a)&(Y[:,0]<t0+a+15)
    if mA.sum()<2 or mL.sum()<2: continue
    pa=np.hypot(np.diff(A[mA,1]),np.diff(A[mA,2])).sum(); pl=np.hypot(np.diff(L[mL,1]),np.diff(L[mL,2])).sum(); py=np.hypot(np.diff(Y[mY,1]),np.diff(Y[mY,2])).sum()
    pw=0 if mW.sum()<2 else ((W[mW][-1]-W[mW][0])[[0,3]]).mean()
    if max(pa,pl,pw)>0.05: print('%4d-%3d  AMCL %.2f  lidar %.2f  wheelM1M4 %.2f  yahboom %.2f   amcl std end %.2f/%.0f°'%(a,a+15,pa,pl,pw,py,A[mA][-1,4],A[mA][-1,6]))
