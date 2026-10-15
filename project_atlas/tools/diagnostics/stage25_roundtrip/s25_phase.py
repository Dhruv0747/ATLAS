import json,math,numpy as np
from s25_load import load
d=load({'/atlas/encoder_update','/atlas/encoder_health','/atlas/control_policy','/yahboom/odom','/odom','/amcl_pose','/lidar/odom','/lidar/odom_raw','/im10a/imu/bias_corrected_candidate','/imu/data','/cmd_vel'})
def yaw(q): return math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
t0=d['/atlas/encoder_update'][0][0]
enc=[(t,json.loads(m.data)) for t,m,_ in d['/atlas/encoder_update']]
et=np.array([t for t,_ in enc]); W=np.array([e['wheel_distances_m'] for _,e in enc])
def path(l):
    p=np.array([(t,m.pose.pose.position.x,m.pose.pose.position.y,yaw(m.pose.pose.orientation)) for t,m,_ in l]); return p
Y=path(d['/yahboom/odom']);E=path(d['/odom']);A=path(d['/amcl_pose']);L=path(d['/lidar/odom']);LR=path(d['/lidar/odom_raw'])
im=np.array([(t,m.angular_velocity.z) for t,m,_ in d['/im10a/imu/bias_corrected_candidate']])
def seg(P,a,b):
    m=(P[:,0]>=t0+a)&(P[:,0]<t0+b); q=P[m]
    if len(q)<2: return None
    pl=np.hypot(np.diff(q[:,1]),np.diff(q[:,2])).sum(); net=math.hypot(q[-1,1]-q[0,1],q[-1,2]-q[0,2])
    dy=np.degrees(np.unwrap(q[:,3])[-1]-np.unwrap(q[:,3])[0]); return pl,net,dy
def gyro(a,b):
    m=(im[:,0]>=t0+a)&(im[:,0]<t0+b); q=im[m]; return np.degrees((q[1:,1]*np.diff(q[:,0])).sum())
def wheel(a,b):
    m=(et>=t0+a)&(et<t0+b); w=W[m]; return (w[-1]-w[0]).tolist()
# 2-wheel (M1,M4) agreement integral for travel estimate
def m14(a,b):
    m=(et>=t0+a)&(et<t0+b); w=W[m]; dm=np.diff(w,axis=0); 
    ok=(dm[:,0]>0)&(dm[:,3]>0)&(np.abs(dm[:,0]-dm[:,3])<=np.maximum(0.004,0.45*np.maximum(dm[:,0],dm[:,3])))
    return dm[ok][:,[0,3]].mean(axis=1).sum(), ok.mean()
print('phase           wheelΔ M1..M4 | M1/M4-agree dist (frac ok) | yahboom path/net/Δyaw | EKF path/net/Δyaw | AMCL path/net/Δyaw | lidar/odom path/net/Δyaw | gyro∫°')
for name,(a,b) in {'outbound 8-58':(8,58),'return1 130-170':(130,170),'return2 200-430':(200,432)}.items():
    f=lambda r:'-' if r is None else '%.2f/%.2f/%+.0f°'%r
    print(name,np.round(wheel(a,b),2).tolist(),'|','%.2f (%.2f)'%m14(a,b),'|',f(seg(Y,a,b)),'|',f(seg(E,a,b)),'|',f(seg(A,a,b)),'|',f(seg(L,a,b)),'|','%+.0f'%gyro(a,b))
# policy vs wheel motion at encoder cadence
pol=[(t,json.loads(m.data)['source']) for t,m,_ in d['/atlas/control_policy']]; pt=np.array([t for t,_ in pol])
src=np.array([pol[max(np.searchsorted(pt,t)-1,0)][1] for t in et[1:]])
moving=(np.abs(np.diff(W,axis=0)).max(axis=1)>0.002)
yv=np.array([m.twist.twist.linear.x for _,m,_ in d['/yahboom/odom']]); yt=np.array([t for t,_,_ in d['/yahboom/odom']])
yvi=np.interp(et[1:],yt,np.abs(yv)); 
print('wheel-moving intervals',moving.sum(),'of',len(moving))
for s in sorted(set(src)): print(' policy',s,'while wheels moving:',int((moving&(src==s)).sum()),' while still:',int((~moving&(src==s)).sum()))
print(' wheels moving but |yahboom vx|<0.02 :',int((moving&(yvi<0.02)).sum()),' of ',int(moving.sum()))
