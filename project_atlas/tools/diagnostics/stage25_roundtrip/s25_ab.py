import sys,glob,math,sqlite3,numpy as np
from rosbags.typesys import Stores,get_typestore
ts=get_typestore(Stores.ROS2_HUMBLE)
R='/mnt/user-data/uploads/Downloads/atlas_stage25_bags/replay/'
def yaw(q): return math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
def odom_from(db,topic='/odom'):
    c=sqlite3.connect('file:'+db+'?mode=ro',uri=True); tid=c.execute("select id from topics where name=?",(topic,)).fetchone()
    if not tid: return None
    rows=[(t/1e9,ts.deserialize_cdr(bytes(d),'nav_msgs/msg/Odometry')) for t,d in c.execute('select timestamp,data from messages where topic_id=? order by timestamp',(tid[0],))]
    return np.array([(m.header.stamp.sec+m.header.stamp.nanosec*1e-9,m.pose.pose.position.x,m.pose.pose.position.y,yaw(m.pose.pose.orientation)) for t,m in rows])
def stats(P,a,b):
    m=(P[:,0]>=a)&(P[:,0]<=b); q=P[m]
    path=np.hypot(np.diff(q[:,1]),np.diff(q[:,2])).sum(); net=math.hypot(q[-1,1]-q[0,1],q[-1,2]-q[0,2]); dy=math.degrees(np.unwrap(q[:,3])[-1]-np.unwrap(q[:,3])[0])
    step=np.hypot(np.diff(q[:,1]),np.diff(q[:,2])).max()
    return path,net,dy,step
if __name__=='__main__':
    from s25_load import load
    d=load({'/odom','/lidar/odom','/im10a/imu/bias_corrected_candidate','/amcl_pose'})
    def arr(k): return np.array([(t,m.pose.pose.position.x,m.pose.pose.position.y,yaw(m.pose.pose.orientation)) for t,m,_ in d[k]])
    rec=arr('/odom'); L=arr('/lidar/odom'); A=arr('/amcl_pose'); im=np.array([(t,m.angular_velocity.z) for t,m,_ in d['/im10a/imu/bias_corrected_candidate']])
    t0=rec[0,0]
    caps={'cap1':(0,59.2),'cap4':(None,None),'cap5':(None,None)}
    import json
    for cap in sorted(glob.glob(R+'cap*')):
        n=cap.split('/')[-1]
        out={}
        for v in ('pose_velocity','velocity_only'):
            db=glob.glob(cap+'/'+v+'/*.db3')
            if db: out[v]=odom_from(db[0])
        if not out: continue
        a=max(out['pose_velocity'][0,0],out['velocity_only'][0,0]); b=min(out['pose_velocity'][-1,0],out['velocity_only'][-1,0])
        g=lambda P: P
        m=(im[:,0]>=a)&(im[:,0]<=b); gy=math.degrees((im[m][1:,1]*np.diff(im[m][:,0])).sum())
        print('=== %s window %.1f..%.1f s (rel first capture t0) duration %.1f s'%(n,a-t0,b-t0,b-a))
        print('%-22s path %.2f m  net %.2f m  Δyaw %+.0f°  max step %.3f m'%('recorded production A',*stats(rec,a,b)))
        for v in out: 
            P=out[v]; print('%-22s path %.2f m  net %.2f m  Δyaw %+.0f°  max step %.3f m'%('replay '+v,*stats(P,a,b)))
        print('%-22s path %.2f m  net %.2f m  Δyaw %+.0f°'%('LiDAR /lidar/odom',*stats(L,a,b)[:3]),'| gyro∫ %+.0f° | AMCL Δyaw %+.0f°'%(gy,stats(A,a,b)[2]))

def pose_at(P,t): return np.array([np.interp(t,P[:,0],P[:,1]),np.interp(t,P[:,0],P[:,2]),np.interp(t,P[:,0],np.unwrap(P[:,3]))])
def rel_vec(P,a,b):
    p0=pose_at(P,a);p1=pose_at(P,b);c,s=math.cos(p0[2]),math.sin(p0[2]);dx,dy=p1[0]-p0[0],p1[1]-p0[1]
    return np.array([c*dx+s*dy,-s*dx+c*dy,math.degrees(p1[2]-p0[2])])
if __name__=='__main__':
    print('\n=== end displacement in START body frame (x forward, y left, yaw deg) and error vs LiDAR-odom / AMCL')
    for cap in sorted(glob.glob(R+'cap*')):
        n=cap.split('/')[-1]; out={}
        for v in ('pose_velocity','velocity_only'):
            db=glob.glob(cap+'/'+v+'/*.db3')
            if db: out[v]=odom_from(db[0])
        if len(out)<2: continue
        a=max(out['pose_velocity'][0,0],out['velocity_only'][0,0])+1.0; b=min(out['pose_velocity'][-1,0],out['velocity_only'][-1,0])-0.5
        srcs={'recorded A':rec,'replay A':out['pose_velocity'],'replay B':out['velocity_only'],'LiDAR odom':L,'AMCL':A}
        V={k:rel_vec(P,a,b) for k,P in srcs.items()}
        print(n,'window %.1f..%.1f s'%(a-t0,b-t0))
        for k,v in V.items(): print('   %-11s x %+6.2f y %+6.2f yaw %+6.0f°   | vs LiDAR: %.2f m  vs AMCL: %.2f m'%(k,v[0],v[1],v[2],math.hypot(*(v[:2]-V['LiDAR odom'][:2])),math.hypot(*(v[:2]-V['AMCL'][:2]))))
