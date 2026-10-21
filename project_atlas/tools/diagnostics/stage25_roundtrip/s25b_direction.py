"""Does a suspect wheel's count sign follow the real direction (set by M1/M4) or stay fixed? One lost quadrature channel => fixed."""
import json,numpy as np
from s25_load import load
d=load({'/atlas/encoder_update'})
enc=d['/atlas/encoder_update']; et=np.array([t for t,_,_ in enc])
R=np.array([json.loads(m.data)['raw_counts'] for _,m,_ in enc],float); S=np.array([json.loads(m.data)['encoder_signs'] for _,m,_ in enc])
for _,m,_ in enc:
    pass
tf=[t for t,m,_ in enc if json.loads(m.data)['raw_counts'][1]==-40584][0]
dR=np.diff(R,axis=0)*S[1:]; ok=np.diff(et)<0.5; tt=et[1:]
ref=(dR[:,0]+dR[:,3])/2
def table(nm,a,b):
    base=ok&(tt>=a)&(tt<b)&(dR[:,0]*dR[:,3]>0)&(np.abs(ref)>=8)       # M1 and M4 agree on direction, clearly moving
    fw=base&(ref>0); rv=base&(ref<0)
    print('\n%s: M1/M4-agreeing moving intervals fwd=%d rev=%d'%(nm,fw.sum(),rv.sum()))
    for k,w in ((1,'M2'),(2,'M3')):
        for lab,m in (('FORWARD',fw),('REVERSE',rv)):
            if m.sum()<3: print('  %s while %s: n=%d (too few)'%(w,lab,m.sum()));continue
            x=dR[m,k]; print('  %s while rover %s: n=%3d  sum %+7.0f  frac(+) %.2f frac(-) %.2f frac(0) %.2f  sum(M1/M4 mean) %+7.0f ratio %.2f'%(w,lab,m.sum(),x.sum(),(x>1).mean(),(x<-1).mean(),(np.abs(x)<=1).mean(),ref[m].sum(),abs(x.sum())/max(abs(ref[m].sum()),1)))
table('PRE-FAULT whole run',et[0],tf-4)
table('POST-FAULT',tf+5,et[-1]+1)
# and M3 through the whole run split in time thirds
for a,b,nm in ((et[0],et[0]+60,'outbound'),(et[0]+60,tf-4,'hall turn'),(tf+5,tf+120,'post +0-120s'),(tf+120,et[-1]+1,'post +120s..end')):
    table('M3 view: '+nm,a,b)
