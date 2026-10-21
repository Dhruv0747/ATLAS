import math,numpy as np
from s25_load import load
d=load({'/amcl_pose','/lidar/odom','/lidar/odom_raw','/odom','/yahboom/odom'})
def yaw(q): return math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
def arr(k): return np.array([(t,m.pose.pose.position.x,m.pose.pose.position.y,yaw(m.pose.pose.orientation)) for t,m,_ in d[k]])
A=arr('/amcl_pose');L=arr('/lidar/odom');LR=arr('/lidar/odom_raw');E=arr('/odom');Y=arr('/yahboom/odom')
t0=A[0,0]
def pose_at(P,t): return np.array([np.interp(t,P[:,0],P[:,1]),np.interp(t,P[:,0],P[:,2]),np.interp(t,P[:,0],np.unwrap(P[:,3]))])
def compose(p,r): c,s=math.cos(p[2]),math.sin(p[2]); return np.array([p[0]+c*r[0]-s*r[1],p[1]+s*r[0]+c*r[1],p[2]+r[2]])
def rel(p0,p1): c,s=math.cos(p0[2]),math.sin(p0[2]); dx,dy=p1[0]-p0[0],p1[1]-p0[1]; return np.array([c*dx+s*dy,-s*dx+c*dy,p1[2]-p0[2]])
ts=A[0,0]+2   # stationary start
checks={'Hall arrival (t=57)':57,'return end (t=438)':438}
for name,P in (('LiDAR /lidar/odom',L),('LiDAR /lidar/odom_raw',LR),('EKF /odom',E),('wheel /yahboom/odom',Y)):
    p0=pose_at(P,t0+2); A0=pose_at(A,t0+2)
    row=[]
    for lab,tt in checks.items():
        r=rel(p0,pose_at(P,t0+tt)); est=compose(A0,r); a=pose_at(A,t0+tt)
        row.append('%s: est (%.2f,%.2f,%.0f°) vs AMCL (%.2f,%.2f,%.0f°) diff %.2f m'%(lab,est[0],est[1],math.degrees(est[2]),a[0],a[1],math.degrees(a[2]),math.hypot(est[0]-a[0],est[1]-a[1])))
    print(name); [print('   ',r) for r in row]
print('start AMCL',pose_at(A,t0+2)); print('end AMCL',pose_at(A,t0+438), 'dist from start %.2f'%math.hypot(*(pose_at(A,t0+438)[:2]-pose_at(A,t0+2)[:2])))
print('lidar/odom span: first',L[0,1:],'last',L[-1,1:],'any resets?',int((np.hypot(np.diff(L[:,1]),np.diff(L[:,2]))>1.0).sum()))
