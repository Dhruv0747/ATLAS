import sqlite3,glob,pickle,sys
from rosbags.typesys import Stores,get_typestore
ts=get_typestore(Stores.ROS2_HUMBLE)
B='/mnt/user-data/uploads/Downloads/atlas_stage25_bags/bags_work/'
def load(topics=None):
    out={}
    seen=set()
    for f in sorted(glob.glob(B+'*/*.db3')):
        c=sqlite3.connect('file:'+f+'?mode=ro',uri=True)
        tp={i:(n,t) for i,n,t in c.execute('select id,name,type from topics')}
        for tid,t,data in c.execute('select topic_id,timestamp,data from messages order by timestamp'):
            n,ty=tp[tid]
            if topics and n not in topics: continue
            k=(n,t)
            if k in seen: continue
            seen.add(k)
            if n=='/particle_cloud': continue
            out.setdefault(n,[]).append((t/1e9, ts.deserialize_cdr(bytes(data),ty), f.split('/')[-2][8:30]))
    return out
if __name__=='__main__':
    d=load({'/atlas/encoder_update','/atlas/encoder_health','/atlas/control_policy','/yahboom/encoder/m1','/cmd_vel'})
    for k in ('/atlas/encoder_update','/atlas/encoder_health','/atlas/control_policy'):
        for i in (0,len(d[k])//2): print(k, d[k][i][0], d[k][i][1].data[:700]); 
    print({k:len(v) for k,v in d.items()})
