import json,math,pickle,numpy as np
from s25_load import load
d=load()
pickle.dump({k:[(t,m) for t,m,_ in v] for k,v in d.items() if k not in('/scan','/scan_raw','/tf','/particle_cloud')},open('s25_small.pkl','wb')) if False else None
def yaw(q): return math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
t0=min(v[0][0] for v in d.values())
enc=[(t,json.loads(m.data)) for t,m,_ in d['/atlas/encoder_update']]
et=np.array([t for t,_ in enc]); wd=np.array([e['wheel_distances_m'] for _,e in enc]); rc=np.array([e['raw_counts'] for _,e in enc])
yo=[(t,m.pose.pose.position.x,m.pose.pose.position.y,yaw(m.pose.pose.orientation),m.twist.twist.linear.x,m.twist.twist.angular.z) for t,m,_ in d['/yahboom/odom']]
eo=[(t,m.pose.pose.position.x,m.pose.pose.position.y,yaw(m.pose.pose.orientation),m.twist.twist.linear.x) for t,m,_ in d['/odom']]
am=[(t,m.pose.pose.position.x,m.pose.pose.position.y,yaw(m.pose.pose.orientation),math.sqrt(m.pose.covariance[0]),math.degrees(math.sqrt(max(m.pose.covariance[35],0)))) for t,m,_ in d['/amcl_pose']]
lo=[(t,m.pose.pose.position.x,m.pose.pose.position.y,yaw(m.pose.pose.orientation)) for t,m,_ in d['/lidar/odom']]
cj=[(t,m.linear.x,m.angular.z) for t,m,_ in d['/cmd_vel_joy']]
cv=[(t,m.linear.x,m.angular.z) for t,m,_ in d['/cmd_vel']]
pol=[(t,json.loads(m.data)['source'],json.loads(m.data)['stop_latched']) for t,m,_ in d['/atlas/control_policy']]
im=[(t,m.angular_velocity.z) for t,m,_ in d['/im10a/imu/bias_corrected_candidate']]
A=lambda l:np.array([x[0] for x in l])
def at(arr,l,col):
    return np.interp(arr,A(l),[x[col] for x in l])
print('t0',t0,'span',et[-1]-et[0])
gap=np.where(np.diff(et)>1.0)[0]
for g in gap: print('GAP in encoder_update %.2f -> %.2f (%.1f s)'%(et[g]-t0,et[g+1]-t0,et[g+1]-et[g]))
bins=np.arange(et[0],et[-1]+5,5)
print(' t(s) clk      cmdjoy(max|v|,max|w|) cmd_vel  dW[m] M1..M4 (signed m)       dYahb dEKF  amcl(x,y,yaw) std   lidarΔ  src  gyroZ∫°')
for a,b in zip(bins[:-1],bins[1:]):
    m=(et>=a)&(et<b)
    if m.sum()<2: print('%5.0f %s (no encoder data)'%(a-t0,__import__('time').strftime('%T',__import__('time').localtime(a)))); continue
    dw=wd[m][-1]-wd[m][0]
    def dd(l):
        i=np.searchsorted(A(l),[a,b-1e-9]); 
        if i[1]-i[0]<1: return float('nan')
        s=l[i[0]];e=l[min(i[1],len(l)-1)]; return math.hypot(e[1]-s[1],e[2]-s[2])
    cjm=[x for x in cj if a<=x[0]<b]; cvm=[x for x in cv if a<=x[0]<b]
    ams=[x for x in am if a<=x[0]<b]; ps=[x[1] for x in pol if a<=x[0]<b]
    ims=[x for x in im if a<=x[0]<b]
    gz=sum(x[1] for x in ims)/max(len(ims),1)*(b-a)*57.296
    print('%5.0f %s (%.2f,%.2f) (%.2f,%.2f) [%+.2f %+.2f %+.2f %+.2f] Y%.2f E%.2f  %s  L%.2f %s %+.0f'%(a-t0,__import__('time').strftime('%T',__import__('time').localtime(a)),
      max([abs(x[1]) for x in cjm] or [0]),max([abs(x[2]) for x in cjm] or [0]),max([abs(x[1]) for x in cvm] or [0]),max([abs(x[2]) for x in cvm] or [0]),
      *dw,dd(yo),dd(eo),
      ('(%.2f,%.2f,%.0f°) %.2f'%(ams[-1][1],ams[-1][2],math.degrees(ams[-1][3]),ams[-1][4])) if ams else '-',dd(lo),
      ('/'.join(sorted(set(ps)))),gz))
