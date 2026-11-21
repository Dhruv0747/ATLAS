"""Phase D (offline, investigation only): could LiDAR ICP odom + IM10A gyro bridge stretches where encoder consensus fails?
Judged leg-by-leg between stationary anchors where AMCL pose fits the map (fit>=0.83, local shift 0.05-0.20 m)."""
import json,math,numpy as np
from s25_load import load
d=load({'/atlas/encoder_update','/yahboom/odom','/odom','/amcl_pose','/lidar/odom','/im10a/imu/bias_corrected_candidate'})
def yaw(q): return math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
t0=d['/atlas/encoder_update'][0][0]
P=lambda k:np.array([(t-t0,m.pose.pose.position.x,m.pose.pose.position.y,yaw(m.pose.pose.orientation)) for t,m,_ in d[k]])
A,L,E,Y=P('/amcl_pose'),P('/lidar/odom'),P('/odom'),P('/yahboom/odom')
G=np.array([(t-t0,m.angular_velocity.z) for t,m,_ in d['/im10a/imu/bias_corrected_candidate']])
def at(Pm,a,b):
    m=(Pm[:,0]>=a)&(Pm[:,0]<=b)
    if m.sum()==0: return None
    q=Pm[m]; return np.array([np.median(q[:,1]),np.median(q[:,2]),math.atan2(np.sin(q[:,3]).mean(),np.cos(q[:,3]).mean())])
anch={'start':(0.5,8),'hall':(126,135),'pause1':(160,170),'pause2':(225,235)}
def rel(p,q):  # q expressed in p's frame
    c,s=math.cos(p[2]),math.sin(p[2]); dx,dy=q[0]-p[0],q[1]-p[1]
    return np.array([c*dx+s*dy,-s*dx+c*dy,(q[2]-p[2]+math.pi)%(2*math.pi)-math.pi])
# gyro heading
gt=G[:,0]; gz=G[:,1]; gh=np.concatenate([[0],np.cumsum(gz[1:]*np.diff(gt))])
gyaw=lambda t:np.interp(t,gt,gh)
# hybrid chain: LiDAR-odom translation magnitude/bearing (relative to its own heading) re-rotated by gyro heading
def hybrid(a,b,psi0):
    m=(L[:,0]>=a)&(L[:,0]<=b); q=L[m]; x=y=0.0; psi=psi0
    for i in range(1,len(q)):
        r=rel(q[i-1,1:],q[i,1:]); h=psi0+gyaw(q[i,0])-gyaw(a)   # gyro heading in leg frame
        # body-frame step rotated by mid gyro heading
        hm=(psi0+gyaw(q[i-1,0])-gyaw(a)+h)/2
        x+=r[0]*math.cos(hm)-r[1]*math.sin(hm); y+=r[0]*math.sin(hm)+r[1]*math.cos(hm)
    return np.array([x,y,psi0+gyaw(b)-gyaw(a)])
names=list(anch); R=[]
print('leg | AMCL anchor displacement (body frame of first anchor) | error vs AMCL: LiDAR-odom, LiDAR+gyro hybrid, EKF A, raw wheel')
for i in range(len(names)-1):
    n1,n2=names[i],names[i+1]; a1,a2=anch[n1],anch[n2]
    pa1,pa2=at(A,*a1),at(A,*a2)
    ref=rel(pa1,pa2)
    out=[]
    for nm,Pm in (('lidar',L),('ekf',E),('wheel',Y)):
        p1,p2=at(Pm,*a1),at(Pm,*a2)
        r=rel(p1,p2); out.append((nm,r))
    # hybrid: leg start at mean of anchor-1 window end, integrate to anchor-2 window start; compare in anchor-1 body frame (heading0 = 0)
    ta=a1[1]; tb=a2[0]
    hy=hybrid(ta,tb,0.0)
    pl=at(L,*a1); pl2=at(L,ta,ta+1e-9) if False else None
    s='%-12s|ref %s'%(n1+'→'+n2,np.round([ref[0],ref[1],math.degrees(ref[2])],2).tolist())
    for nm,r in out:
        e=math.hypot(r[0]-ref[0],r[1]-ref[1]); de=math.degrees((r[2]-ref[2]+math.pi)%(2*math.pi)-math.pi)
        s+=' | %s err %.2f m (%.0f%% of |ref| %.2f) dyaw err %+.0f°'%(nm,e,100*e/max(math.hypot(ref[0],ref[1]),1e-6),math.hypot(ref[0],ref[1]),de)
    e=math.hypot(hy[0]-ref[0],hy[1]-ref[1]); de=math.degrees((hy[2]-ref[2]+math.pi)%(2*math.pi)-math.pi)
    s+=' | hybrid err %.2f m (%.0f%%) dyaw err %+.0f°'%(e,100*e/max(math.hypot(ref[0],ref[1]),1e-6),de)
    print(s)
# whole-run chain to pause2 vs AMCL, and residual 'wheel-blind' legs where distance is small
