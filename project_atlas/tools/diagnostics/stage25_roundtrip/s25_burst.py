import json,numpy as np,bisect
from s25_load import load
d=load({'/atlas/encoder_update','/atlas/encoder_health','/steering/mode','/steering/front_angle_deg','/steering/rear_angle_deg','/cmd_vel_joy','/cmd_vel','/yahboom/odom','/joy'})
t0=d['/atlas/encoder_update'][0][0]
def ser(k,f): return np.array([t for t,_,_ in d[k]]),[f(m) for _,m,_ in d[k]]
st,sm=ser('/steering/mode',lambda m:m.data); ft,fa=ser('/steering/front_angle_deg',lambda m:m.data); rt,ra=ser('/steering/rear_angle_deg',lambda m:m.data)
ct,cl=ser('/cmd_vel',lambda m:(m.linear.x,m.angular.z)); jt,jl=ser('/cmd_vel_joy',lambda m:(m.linear.x,m.angular.z))
yt,yl=ser('/yahboom/odom',lambda m:(m.pose.pose.position.x,m.twist.twist.linear.x,m.twist.twist.angular.z))
ht,hl=ser('/atlas/encoder_health',lambda m:json.loads(m.data))
enc=[(t,json.loads(m.data)) for t,m,_ in d['/atlas/encoder_update']]
def near(arr,l,t): i=min(max(np.searchsorted(arr,t)-1,0),len(l)-1); return l[i]
for name,(a,b) in {'outbound mid':(18,22),'return burst A':(247,254),'return burst B':(257,262),'return spin?':(397,402)}.items():
    print('=====',name)
    last=None
    for t,e in enc:
        if t0+a<=t<t0+b:
            if last is not None:
                dt=t-last[0]; dd=np.array(e['wheel_distances_m'])-np.array(last[1]['wheel_distances_m'])
                h=near(ht,hl,t)
                if abs(dd).max()>0.004 or int(t*10)%5==0:
                    print('%6.2f'%(t-t0),'dW',np.round(dd,3).tolist(),'v',np.round(dd/dt,2).tolist(),'steer',near(ft,fa,t),near(rt,ra,t),near(st,sm,t),'cmd',np.round(near(ct,cl,t),2).tolist(),'cons',h['consensus_state'],h['consensus_rejected_encoders'],'ydx v',np.round(near(yt,yl,t)[1:],2).tolist())
            last=(t,e)
