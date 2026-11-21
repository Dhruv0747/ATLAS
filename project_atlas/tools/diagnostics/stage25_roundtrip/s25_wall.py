import math,numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt
from s25_load import load
d=load({'/scan','/scan_raw','/amcl_pose'})
def yaw(q): return math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
img=np.array(Image.open('/mnt/user-data/uploads/Downloads/atlas_recovery_20261015/atlas_latest.pgm')); res=0.05; ox,oy=-3.89,-8.46; h,w=img.shape
occ=(img<=10); DT=distance_transform_edt(~occ)*res
def dt_at(x,y):
    c=((x-ox)/res).astype(int); r=(h-1-((y-oy)/res)).astype(int)
    ok=(c>=0)&(c<w)&(r>=0)&(r<h); out=np.full(x.shape,np.nan); out[ok]=DT[r[ok],c[ok]]; return out
A=np.array([(t,m.pose.pose.position.x,m.pose.pose.position.y,yaw(m.pose.pose.orientation)) for t,m,_ in d['/amcl_pose']])
t0=A[0,0]
def pose(t):
    i=np.searchsorted(A[:,0],t); i=min(max(i,1),len(A)-1); a,b=A[i-1],A[i]; f=(t-a[0])/max(b[0]-a[0],1e-6); f=min(max(f,0),1)
    dy=(b[3]-a[3]+math.pi)%(2*math.pi)-math.pi; return a[1]+f*(b[1]-a[1]),a[2]+f*(b[2]-a[2]),a[3]+f*dy,abs(t-a[0])
def endpoints(m,t,p):
    ang=m.angle_min+np.arange(len(m.ranges))*m.angle_increment; r=np.array(m.ranges,float); ok=np.isfinite(r)&(r>0.2)&(r<8)
    x,y,yw,_=p; lx,ly,lyaw=-0.05,0.0,math.pi    # laser in base_link
    a=ang[ok]+lyaw; px=lx+r[ok]*np.cos(a); py=ly+r[ok]*np.sin(a)
    return x+px*math.cos(yw)-py*math.sin(yw), y+px*math.sin(yw)+py*math.cos(yw)
def stat(topic,a,b,label):
    res_all=[];nsc=0;speeds=[]
    for t,m,_ in d[topic]:
        if t0+a<=t<t0+b:
            p=pose(t); ex,ey=endpoints(m,t,p); v=dt_at(ex,ey); v=v[np.isfinite(v)]
            if len(v)>30: res_all.append(v); nsc+=1
    if not res_all: print(label,'no scans'); return
    v=np.concatenate(res_all); print('%-38s %s scans %3d beams %5d | median DT %.3f  p75 %.3f  frac<=0.05 %.2f  frac<=0.10 %.2f  frac>0.20 %.2f'%(label,topic,nsc,len(v),np.median(v),np.percentile(v,75),(v<=.05).mean(),(v<=.10).mean(),(v>.20).mean()))
for topic in ('/scan','/scan_raw'):
    stat(topic,0,8,'stationary start (AMCL std .01)')
    stat(topic,10,22,'moving outbound 10-22 s (AMCL interp)')
    stat(topic,436,450,'stationary end (corridor)')

print('\n=== local pose refinement of stationary windows (single-window median scan, +-0.8 m, +-20 deg) ===')
def window_scan(a,b):
    R=[]
    for t,m,_ in d['/scan']:
        if t0+a<=t<t0+b: R.append(np.array(m.ranges,float))
    if not R: return None
    R=np.array(R); R[~np.isfinite(R)]=np.nan
    with np.errstate(all='ignore'): med=np.nanmedian(R,axis=0)
    return med, m
def fitscore(rng,m,x,y,yw,thr=0.07):
    ang=m.angle_min+np.arange(len(rng))*m.angle_increment; ok=np.isfinite(rng)&(rng>0.2)&(rng<8)
    a=ang[ok]+math.pi; px=-0.05+rng[ok]*np.cos(a); py=rng[ok]*np.sin(a)
    ex=x+px*math.cos(yw)-py*math.sin(yw); ey=y+px*math.sin(yw)+py*math.cos(yw); v=dt_at(ex,ey); v=v[np.isfinite(v)]
    return (v<=thr).mean() if len(v) else 0, len(v)
for label,(a,b) in {'start (0-8 s)':(0,8),'Hall stop (49-58 s)':(49,58),'return pause (160-170 s)':(160,170),'return pause (225-235 s)':(225,235),'end (436-450 s)':(436,450)}.items():
    ws=window_scan(a,b)
    if ws is None: print(label,'no scan'); continue
    rng,m=ws; p=pose((a+b)/2+t0); base,n=fitscore(rng,m,p[0],p[1],p[2])
    best=(base,0,0,0)
    for dx in np.arange(-0.8,0.81,0.05):
        for dy in np.arange(-0.8,0.81,0.05):
            for dyaw in np.radians(np.arange(-20,21,2)):
                s,_=fitscore(rng,m,p[0]+dx,p[1]+dy,p[2]+dyaw)
                if s>best[0]: best=(s,dx,dy,dyaw)
    print('%-26s AMCL (%.2f,%.2f,%.0f°) fit(<=0.07) %.2f over %d beams | best local fit %.2f at dx %+.2f dy %+.2f dyaw %+.0f° (shift %.2f m)'%(label,p[0],p[1],math.degrees(p[2]),base,n,best[0],best[1],best[2],math.degrees(best[3]),math.hypot(best[1],best[2])))
